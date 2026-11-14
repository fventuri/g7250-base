# Control Unit — main() control flow

Function: `FUN_08021E74` (candidate `main`, HIGH CONFIDENCE).
Evidence: `control_unit/analysis/flow/main_decompile.txt`, strings.

**Bare-metal, no RTOS.** Init then infinite superloop. VERIFIED.

This MCU is the **touchscreen front panel / human interface**.

## Boot sequence (in order)

1. **MPU configuration** — builds an `MPU_Region_InitTypeDef` and calls
   `FUN_08024DB8` (≈ `HAL_MPU_ConfigRegion`) for 5 regions, then
   `FUN_08024D98(4)` (≈ enable). Region base addresses:
   `0x20000000` (DTCM), `0x24000000` (AXI SRAM, attr `0x12`),
   `0x30000000` (D2 SRAM), `0x38000000` (D3 SRAM), and **`0xC0000000`**
   (FMC external memory — size code `0x18` ⇒ 32 MiB; display
   SDRAM/framebuffer). HIGH CONFIDENCE.
2. **Enable Cortex-M7 I-cache + D-cache** (same `SCB->CCR` sequence as
   the Main Unit; SCB `0xE000ED00`). VERIFIED.
3. ~28 subsystem init calls (`FUN_08024BB4` … `FUN_080348DC`) — not yet
   individually identified.
4. Start the hardware-timer "services" and peripherals, with a VT100
   console banner (`\x1b[2J`, `\x1b[H`, `[OK] System started.`).
5. Enter the superloop.

## Hardware-timer "services" (bare-metal periodic tasks)

Named directly by boot-log strings (VERIFIED strings; timer→role
mapping HIGH CONFIDENCE):

| Timer | Service | Purpose |
| --- | --- | --- |
| TIM13 | SLIP Client | inter-MCU link to the Main Unit |
| TIM5 | Audio Service | audio path |
| TIM8 | hm133 | mic/keypad service — shipped mic is the **H-22** (manual); "hm133" is the legacy internal name for Xiegu's mic serial protocol |
| TIM14 | InputDev Service | input devices |
| TIM3 | GT911 CTP Service | Goodix GT911 capacitive touch panel |
| TIM2 | Encoder Service | rotary encoders |

Also: **SPI FatFS** (`[INF] SPI fatfs init`) with `config.ini` on volume
`1:/` (SD card / SPI flash). GT911 has an error path
`gt911_init(), TIM3 is not started`.

## Superloop

Each iteration (`do { … } while(true)`):

- Refresh **IWDG** (`*(0x58004800) = 0xAAAA`). VERIFIED.
- Service calls: `FUN_08042C20`, `FUN_08046CD8`, `FUN_080478D0`,
  `FUN_0803ED20`, `FUN_0804E4E8`, `FUN_080365A0`, `FUN_0803E76C`, then a
  conditional branch on `*pcVar1`, then UI/dispatch
  (`FUN_080366B0`, `FUN_080332C8`, `FUN_08034680`, `FUN_08034C0C`).

`FUN_08024C20(ms)` ≈ `HAL_Delay` (called `(10)`, `(3000)`).
`FUN_08021840(level, msg)` / `FUN_0802DDA4(msg)` = console logger
(HIGH CONFIDENCE).

## Version

Strings: `VER: V1.0.1   DATE: %s   TIME: %s`, `V1.0.0`.

## Unknowns

- Identify the ~28 init functions (step 3) and the UI dispatch functions.
- Display controller behind the FMC region (`0xC0000000`).
- SLIP client command set (shared with Main Unit; Phase 5).
- PLL / SystemClock_Config (as on the Main Unit, not yet located).
