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
3. **HAL bring-up** (HIGH CONFIDENCE; table in
   `analysis/flow/init_sequence.csv`):
   HAL_Init `FUN_08024bb4` → SystemClock_Config `FUN_08021d98` → GPIO
   `FUN_080210d8` → DMA1 NVIC (IRQ 11–13) → DMA2D (RGB565) → FMC SDRAM
   `FUN_08020ecc` (32 MiB, 16-bit, 4 banks, CAS 2, SDCLK = HCLK/2) →
   I2C1 (GT911) → I2C2 (AIC3204 codec) → RTC → SDMMC1 handle (4-bit) →
   SPI1 → TIM2 encoder → TIM3 → TIM4 PWM (PD12/PD13) → TIM8 input
   capture (mic serial line) → TIM13 → TIM14 → USART1 → USART2 → CRC →
   I²S2 (48 kHz) → LTDC `FUN_08021878` (1024×600 RGB565, HSYNC 20 /
   HBP 140 / HFP 160, VSYNC 3 / VBP 20 / VFP 12, framebuffer at
   0xC0000000) → application objects → USB device `FUN_0803d90c`
   (OTG_FS, mass-storage class) → TIM5 → TIM7 → USART2 RX `FUN_080348dc`
   into a 4 KiB D3-SRAM buffer (on failure: abort, de-init, 10 ms,
   retry).
3b. **Services and drivers:**
   1. TIM13 SLIP client, then the banner;
   2. SDRAM command sequence;
   3. AIC3204 codec init (I2C2 0x18, reset PH2) and I²S2 DMA start;
   4. TIM5 audio service;
   5. FatFS mount of the SPI flash;
   6. GUI library init;
   7. backlight PWM set to 50 % (HYPOTHESIS);
   8. TIM8 mic capture, then TIM14;
   9. GT911 init, followed by TIM3 if it succeeds;
   10. TIM2 encoders;
   11. settings/INI loads;
   12. version banner.
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

Also: **SPI FatFS**. The boot log reports its init; the configuration
file is on volume `1:`, the SPI flash (see `storage.md`). If the GT911
init fails, the boot log says so and the touch-poll timer TIM3 stays off.

## Superloop

Each iteration (`do { … } while(true)`):

- Refresh **IWDG** (`*(0x58004800) = 0xAAAA`). VERIFIED.
- Service calls: `FUN_08042C20`, `FUN_08046CD8`, `FUN_080478D0`,
  `FUN_0803ED20`, `FUN_0804E4E8`, `FUN_080365A0`, `FUN_0803E76C`, then a
  conditional branch on `*pcVar1`, then UI/dispatch
  (`FUN_080366B0`, `FUN_080332C8`, `FUN_08034680`, `FUN_08034C0C`).

`FUN_08024C20(ms)` ≈ `HAL_Delay` (called `(10)`, `(3000)`).
`FUN_08021840(level, msg)` = console logger; `FUN_0802DDA4(htim)` = HAL_TIM_Base_Start_IT (not a logger)
(HIGH CONFIDENCE).

## Version

Strings: `VER: V1.0.1   DATE: %s   TIME: %s`, `V1.0.0`.

## Clock configuration — `FUN_08021d98` (SystemClock_Config), VERIFIED

`main` (`FUN_08021e74`) calls it. It runs in this order:
1. **Supply:** LDO only (`FUN_08029ba4`, value 2).
2. **Voltage scaling:** Scale 1, then SYSCFG_PWRCR.ODEN = 1, then a wait
   for VOSRDY. This is the H743 rev-V way to reach Scale 0.
3. **Backup domain and LSE:** backup-domain access is enabled and the
   LSE drive is set high.
4. **Oscillators and PLL:** OscConfig (`FUN_08029ce0`).
5. **Bus clocks:** ClockConfig (`FUN_0802a3e0`), flash latency 4.

| Item | Setting | Result |
| --- | --- | --- |
| HSE | on, crystal; built for 25 MHz | 25 MHz |
| LSE / HSI48 | on / on | RTC / USB |
| PLL1 | from HSE, M=5 N=192 P=2 Q=10 R=2, input range 4–8 MHz | VCO 960 MHz; P 480, Q 96, R 480 MHz |
| SYSCLK / CPU | PLL1P | **480 MHz** |
| HCLK | /2 | **240 MHz** |
| PCLK1/2/3/4 | all /2 | **120 MHz** (timer clocks 240 MHz) |
| PLL2 | M=25 N=240 P=2 Q=2 R=1 | VCO 240 MHz; R = 240 MHz (FMC) |
| PLL3 | M=25 N=200 P=2 Q=2 R=5 | VCO 200 MHz; R = 40 MHz (LTDC) |

| Kernel clock | Source | Rate | Set in |
| --- | --- | --- | --- |
| FMC (SDRAM) | PLL2R | 240 MHz | `FUN_08020f38` |
| LTDC pixel clock | PLL3R | 40 MHz | `FUN_08021928` |
| SDMMC1 | PLL1Q | 96 MHz | `FUN_08022340` |
| SPI1/2 | PLL1Q | 96 MHz | `FUN_08022630`, `FUN_080216c4` |
| USARTs | PCLK2 / PCLK1 | 120 MHz | `FUN_08023344` |
| I2C1/3 | PCLK1 | 120 MHz | `FUN_080214f0` |
| USB OTG_FS | HSI48 | 48 MHz | `FUN_0803dc10` |
| RTC | LSE | 32.768 kHz | `FUN_080222c0` |

PLL2 and PLL3 run from a 1 MHz reference with the wide-VCO range
selected. The reference manual expects the medium range below 2 MHz,
so this setup may be slightly out of spec (MEDIUM CONFIDENCE).
Values are in `analysis/clocks/clock_config.csv`.

## Unknowns

- Identify the ~28 init functions (step 3) and the UI dispatch functions.
- Display controller behind the FMC region (`0xC0000000`).
- SLIP client command set (shared with Main Unit; Phase 5).

## Interrupt paths — VERIFIED

| IRQ | Path |
| --- | --- |
| 8 | clears EXTI pending bit 2, then the GT911 callback (`0x08035798`) |
| 11 / 12 / 13 | HAL DMA on the I²S2 RX/TX and USART2 TX handles (`FUN_08052830` installs the I²S callbacks) |
| 29 | GT911 poll `FUN_08035ce8`, then HAL TIM |
| 38 | HAL UART (USART2) |
| 44 | HAL TIM on TIM8, then on TIM13 (SLIP client callback) |
| 45 | when TIM14 updates: key scan `FUN_08035f80` and input services, every 10th tick `FUN_08036674`; then HAL TIM |
| 46 | CC1: mic-line decoder `FUN_08035e2c` with period and pulse; CC2: latch the pulse; then HAL TIM |
| 49 | HAL SD |
| 50 | HAL TIM, then the audio service `FUN_08050cb0` |
| 55 | CW text-keyer step `FUN_08052364`, then HAL TIM |
| 88 | HAL LTDC |
| 101 | HAL PCD (USB) |

## SWR scanner (APP menu) — VERIFIED

The scanner runs entirely on the Control Unit (`FUN_08045d8c`).

**Start.**
1. Save frequency, mode, TX power and AF gain.
2. Mute the audio.
3. Force NFM (a steady carrier) and 5 W.
4. Key the Main Unit through `0x01` byte `0x15E` bit 6. Main maps this
   to its SWR-scan PTT, which also bypasses the band table.

**Sweep.**
- 51 points around the start frequency: centre ± 25 steps, with a step
  of 1, 2 or 5 kHz selected by a button.
- 500 ms dwell on the first point and 100 ms on the others.
- The SWR from the `0x03` meter tail is recorded at each point into a
  chart widget.
- The sweep loops until stopped.

**Stop.** Bit 6 is cleared and the saved settings are restored.

**Why this needed the firmware:** sweep geometry, timing and the backup
set are UI-firmware choices.
