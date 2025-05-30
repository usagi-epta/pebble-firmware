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

#include <stdint.h>
#include <stdbool.h>

typedef enum BootBitValue {
  BOOT_BIT_INITIALIZED = 0x1 << 0,
  BOOT_BIT_NEW_FW_AVAILABLE = 0x1 << 1,
  BOOT_BIT_NEW_FW_UPDATE_IN_PROGRESS = 0x1 << 2,
  BOOT_BIT_FW_START_FAIL_STRIKE_ONE = 0x1 << 3,
  BOOT_BIT_FW_START_FAIL_STRIKE_TWO = 0x1 << 4,
  BOOT_BIT_RECOVERY_LOAD_FAIL_STRIKE_ONE = 0x1 << 5,
  BOOT_BIT_RECOVERY_LOAD_FAIL_STRIKE_TWO = 0x1 << 6,
  BOOT_BIT_RECOVERY_START_IN_PROGRESS = 0x1 << 7,
  BOOT_BIT_STANDBY_MODE_REQUESTED = 0x1 << 8,
  BOOT_BIT_SOFTWARE_FAILURE_OCCURRED = 0x1 << 9,
  BOOT_BIT_NEW_SYSTEM_RESOURCES_AVAILABLE = 0x1 << 10,
  BOOT_BIT_RESET_LOOP_DETECT_ONE = 0x1 << 11,
  BOOT_BIT_RESET_LOOP_DETECT_TWO = 0x1 << 12,
  BOOT_BIT_RESET_LOOP_DETECT_THREE = 0x1 << 13,
  BOOT_BIT_FW_STABLE = 0x1 << 14,
  BOOT_BIT_NEW_FW_INSTALLED = 0x1 << 15,
  BOOT_BIT_STANDBY_MODE_ENTERED = 0x1 << 16,
  BOOT_BIT_FORCE_PRF = 0x1 << 17,
  BOOT_BIT_NEW_PRF_AVAILABLE = 0x1 << 18
} BootBitValue;

void boot_bit_init();
void boot_bit_set(BootBitValue bit);
void boot_bit_clear(BootBitValue bit);
bool boot_bit_test(BootBitValue bit);

// Dump the contents to PBL_LOG
void boot_bit_dump(void);
uint32_t boot_bits_get(void);

void boot_version_write(void);
uint32_t boot_version_read(void);
