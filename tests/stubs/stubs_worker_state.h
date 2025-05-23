/*
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#pragma once

#include "util/heap.h"

static Heap s_worker_heap;

Heap* worker_state_get_heap(void) {
  return &s_worker_heap;
}

struct tm *worker_state_get_gmtime_tm(void) {
  static struct tm gmtime_tm = {0};
  return &gmtime_tm;
}
struct tm *worker_state_get_localtime_tm(void) {
  static struct tm localtime_tm = {0};
  return &localtime_tm;
}
char *worker_state_get_localtime_zone(void) {
  static char localtime_zone[TZ_LEN] = {0};
  return localtime_zone;
}

