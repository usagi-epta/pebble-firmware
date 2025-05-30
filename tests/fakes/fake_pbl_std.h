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
#include "util/time/time.h"


struct tm *pbl_override_localtime(const time_t *timep) {
  static struct tm local_tm;
  localtime_r(timep, &local_tm);
  return &local_tm;
}

struct tm *pbl_override_gmtime(const time_t *timep) {
  static struct tm local_tm;
  gmtime_r(timep, &local_tm);
  return &local_tm;
}

time_t pbl_override_mktime(struct tm *tb) {
  return mktime(tb);
}

