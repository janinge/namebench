# Copyright 2009 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A base user-interface workflow, to be inherited by UI modules."""

import tempfile

import addr_util
import benchmark
import better_webbrowser
import config
import data_sources
import geoip
import nameserver
import reporter
import providers
import site_connector
import util

DEFAULT_DISTANCE_KM=2000

__author__ = 'tstromberg@google.com (Thomas Stromberg)'


class BaseUI(object):
  """Common methods for all UI implementations."""

  def __init__(self):
    self.SetupDataStructures()

  def SetupDataStructures(self):
    """Instead of requiring users to inherit __init__(), this sets up structures."""
    self.reporter = None
    self.nameservers = None
    self.bmark = None
    self.report_path = None
    self.csv_path = None
    self.geodata = None
    self.country = None
    self.sources = {}
    self.url = None
    self.share_state = None
    self.test_records = []

  def UpdateStatus(self, msg, **kwargs):
    """Update the little status message on the bottom of the window."""
    if hasattr(self, 'status_callback') and self.status_callback:
      self.status_callback(msg, **kwargs)
    else:
      print msg

  def DebugMsg(self, message):
    self.UpdateStatus(message, debug=True)

  def LoadDataSources(self):
    self.data_src = data_sources.DataSources(status_callback=self.UpdateStatus)

  def PrepareTestRecords(self):
    """Figure out what data source a user wants, and create test_records."""
    if self.options.input_source:
      src_type = self.options.input_source
    else:
      src_type = self.data_src.GetBestSourceDetails()[0]
      self.options.input_source = src_type

    self.test_records = self.data_src.GetTestsFromSource(
        src_type,
        self.options.query_count,
        select_mode=self.options.select_mode
    )

  def GatherNameServerData(self):
    """Build a nameserver data set from config and other sources."""

    ns_data = config.GetNameServerData()
    for i, ip in enumerate(self.options.servers):
      ns = nameserver.NameServer(ip, tags=['specified'], name='USR%s-%s' % (i, ip))
      ns_data.append(ns)
    return ns_data

  def PrepareNameServers(self, distance=DEFAULT_DISTANCE_KM):
    """Setup self.nameservers to have a list of healthy fast servers."""
    self.nameservers = self.GatherNameServerData()
    require_tags = set()
    include_tags = set(['specified'])

    if self.options.ipv6_only:
      require_tags.add('ipv6')
    elif self.options.ipv4_only:
      require_tags.add('ipv4')

    if self.options.include_system or self.options.include_all:
      include_tags.update(set(['system', 'dhcp']))

    if self.options.include_regional or self.options.include_all:
      if not self.geodata:
        self.DiscoverLocation()
      self.nameservers.SetClientLocation(self.geodata.get('latitude'),
                                         self.geodata.get('longitude'),
                                         self.geodata.get('country_code'))
      client_ip = providers.MyResolverInfo().ClientIp()
      local_ns = providers.SystemResolver()
      hostname = local_ns.GetReverseIp(client_ip)
      self.nameservers.SetNetworkLocation(addr_util.GetDomainFromHostname(hostname),
                                          local_ns.GetAsnForIp(client_ip))

      include_tags.update(set(['regional', 'internal', 'global']))

    if self.options.include_global or self.options.include_all:
      include_tags.update(set(['preferred', 'global']))

    self.nameservers.status_callback = self.UpdateStatus
    self.nameservers.FilterByTag(include_tags=include_tags,
                                 require_tags=require_tags)
    if self.options.include_regional or self.options.include_all:
      self.nameservers.FilterByProximity(max_distance=DEFAULT_DISTANCE_KM)
    self.nameservers.SetTimeouts(self.options.timeout,
                                 self.options.ping_timeout,
                                 self.options.health_timeout)
    self.nameservers.CheckHealth(sanity_checks=config.GetSanityChecks())

  def PrepareBenchmark(self):
    """Setup the benchmark object with the appropriate dataset."""
    if len(self.nameservers) == 1:
      thread_count = 1
    else:
      thread_count = self.options.benchmark_thread_count

    self.bmark = benchmark.Benchmark(self.nameservers,
                                     query_count=self.options.query_count,
                                     run_count=self.options.run_count,
                                     thread_count=thread_count,
                                     status_callback=self.UpdateStatus)

  def RunBenchmark(self):
    """Run the benchmark."""
    results = self.bmark.Run(self.test_records)
    index = []
    if self.options.upload_results in (1, True):
      connector = site_connector.SiteConnector(self.options, status_callback=self.UpdateStatus)
      index_hosts = connector.GetIndexHosts()
      if index_hosts:
        index = self.bmark.RunIndex(index_hosts)
      else:
        index = []
      self.DiscoverLocation()
      if len(self.nameservers) > 1:
        self.nameservers.RunPortBehaviorThreads()

    self.reporter = reporter.ReportGenerator(self.options, self.nameservers,
                                             results, index=index, geodata=self.geodata)

  def DiscoverLocation(self):
    if not getattr(self, 'geodata', None):
      self.geodata = geoip.GetGeoData()
      self.country = self.geodata.get('country_name', None)
    return self.geodata

  def RunAndOpenReports(self):
    """Run the benchmark and open up the report on completion."""
    self.RunBenchmark()
    best = self.reporter.BestOverallNameServer()
    self.CreateReports()
    if self.options.template == 'html':
      self.DisplayHtmlReport()
    if self.url:
      self.UpdateStatus('Complete! Your results: %s' % self.url)
    else:
      self.UpdateStatus('Complete! %s [%s] is the best.' % (best.name, best.ip))

  def CreateReports(self):
    """Create CSV & HTML reports for the latest run."""

    if self.options.output_file:
      self.report_path = self.options.output_file
    else:
      self.report_path = util.GenerateOutputFilename(self.options.template)

    if self.options.csv_file:
      self.csv_path = self.options_csv_file
    else:
      self.csv_path = util.GenerateOutputFilename('csv')

    if self.options.upload_results in (1, True):
      # This is for debugging and transparency only.
      self.json_path = util.GenerateOutputFilename('js')
      self.UpdateStatus('Saving anonymized JSON to %s' % self.json_path)
      json_data = self.reporter.CreateJsonData()
      f = open(self.json_path, 'w')
      f.write(json_data)
      f.close()

      self.UpdateStatus('Uploading results to %s' % self.options.site_url)
      connector = site_connector.SiteConnector(self.options, status_callback=self.UpdateStatus)
      self.url, self.share_state = connector.UploadJsonResults(
          json_data,
          hide_results=self.options.hide_results
      )

      if self.url:
        self.UpdateStatus('Your sharing URL: %s (%s)' % (self.url, self.share_state))

    self.UpdateStatus('Saving report to %s' % self.report_path)
    f = open(self.report_path, 'w')
    self.reporter.CreateReport(format=self.options.template,
                               output_fp=f,
                               csv_path=self.csv_path,
                               sharing_url=self.url,
                               sharing_state=self.share_state)
    f.close()

    self.UpdateStatus('Saving detailed results to %s' % self.csv_path)
    self.reporter.SaveResultsToCsv(self.csv_path)

  def DisplayHtmlReport(self):
    self.UpdateStatus('Opening %s' % self.report_path)
    better_webbrowser.output = self.DebugMsg
    better_webbrowser.open(self.report_path)

