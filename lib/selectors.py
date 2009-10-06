#!/usr/bin/env python
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

import math
import random

# When running a weighted distribution, never repeat a domain more than this:
MAX_REPEAT = 3

def MaxRepeatCount(elements, count):
  # If we're asked to be crazy, lets be crazy.
  if count > (len(elements) * MAX_REPEAT):
    return 2**32
  else:
    return MAX_REPEAT

def WeightedDistribution(elements, count):
  """Given a set of elements, return a weighted distribution back.

  Args:
    elements: A list of elements to choose from
    count: how many elements to return

  Returns:
    A random but fairly distributed list of elements of count count.

  The distribution is designed to mimic real-world DNS usage. The observed
  formula for request popularity was:

  522.520776 * math.pow(x, -0.998506)-2
  """

  def FindY(x, total):
    return total * math.pow(x, -0.408506)

  total = len(elements)
  picks = []
  picked = {}
  offset = FindY(total, total)
  max_repeat = MaxRepeatCount(elements, count)
  while len(picks) < count:
    x = random.random() * total
    y = FindY(x, total) - offset
    index = abs(int(y))
    if index < total:
      if picked.get(index, 0) < max_repeat:
        picks.append(elements[index])
        picked[index] = picked.get(index, 0) + 1
#        print '%s: %s' % (index, elements[index])
  return picks


def ChunkSelect(elements, count):
  """Return a random count-sized contiguous chunk of elements."""
  if len(elements) <= count:
    return elements
  start = random.randint(0, len(elements) - count)
  return elements[start:start + count]

def RandomSelect(elements, count):
  picks = []
  picked = {}

  max_repeat = MaxRepeatCount(elements, count)
  while len(picks) < count:
    choice = random.choice(elements)
    if picked.get(choice, 0) < max_repeat:
      picks.append(choice)
      picked[choice] = picked.get(choice, 0) + 1
  return picks
