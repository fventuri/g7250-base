# Main Unit — main() control flow

Function: `FUN_0802239C` (candidate `main`, HIGH CONFIDENCE).
Evidence: `main_unit/analysis/flow/main_decompile.txt`,
`clock_init_08027774.txt`, strings.

**Bare-metal, no RTOS.** `main()` runs init then an infinite superloop.
VERIFIED (the function never returns; ends in `do { … } while(true)`).

## Boot sequence (in order)

1. If in privileged mode, disable interrupts (`enableIRQinterrupts(0)`).
2. Early setup: MPU (`FUN_0804a7c0`: 4 regions at 0x60000000, the D2
   SRAM, the backup SRAM and the D3 SRAM), stdout unbuffered
   (`FUN_08053b3c`), then the 104-byte slave-info block at `0x24018F30`
   is filled with the MCU and FPGA versions and the build date/time
   (`FUN_08053f64/08053fb6/08053ca4`). HIGH CONFIDENCE.
3. **Enable Cortex-M7 I-cache then D-cache** via `SCB->CCR` (SCB base
   `0xE000ED00`): invalidate (`ICIALLU` @+0x250, `DCISW` set/way loop
   @+0x260), set `CCR.IC` (bit 17) and `CCR.DC` (bit 16), with DSB/ISB.
   VERIFIED.
4. `FUN_08027774` = HAL_Init (priority grouping, tick, HAL_MspInit `FUN_080233e0`).
5. **HAL bring-up in CubeMX order** (HIGH CONFIDENCE; the full table
   with handles is in `analysis/flow/init_sequence.csv`):
   SystemClock_Config `FUN_080222f0` → GPIO + EXTI `FUN_08021470` →
   DMA1/DMA2 `FUN_080213ac` (DMA2 Stream5 memory-to-memory) → MDMA
   channels 0–4 `FUN_08022dc8` (polled) → BDMA NVIC (IRQ 129/130)
   `FUN_080211bc` → I²S3 → USART1 → ADC1 → USART2 → I2C3 → CRC → DAC1
   → I2C1 → UART4 → I2C2 → TIM5 → TIM6 → TIM7 → TIM17 → RTC (time and
   date only) → SPI2 → SPI6 → SPI1 → TIM4 PWM CH1 on PD12 (PSC 54, ARR
   250, 19.92 kHz, pulse 0, never started) → extra GPIOs `FUN_08021830` (PH11, PA8, PC8).
5b. **Application bring-up.** The boot log prints each "[OK] …" header
   *before* the step it names, whatever the result; only the ADC
   calibration line reports the outcome. The order is:
   1. console USART1 RX on circular DMA into a 1 KiB ring in D2 SRAM;
   2. the banner; PH9 is driven high, then a 1 s wait;
   3. AXP223 PSU;
   4. CRC-8 table;
   5. settings, calibration and NVPARAM from the EEPROM;
   6. VersaClock 6 (the log names the 5P49V6965);
   7. CH394 init and IP setup, then the LAN service (UDP socket);
   8. SPI1 latch devices;
   9. ATU table;
   10. DSP tables;
   11. TIM7;
   12. ADC calibration and ADC DMA;
   13. AIC3204 codec;
   14. TRX hardware setup (`FUN_0803e2f4`), then the audio processor
       (`FUN_08033334`);
   15. TIM5, TIM6 and TIM17 (HAL_TIM_Base_Start_IT `FUN_0802f9cc`);
   16. FPGA init `FUN_0803a3a0`: bus test and version;
   17. PH15 is driven low and PH13 high.
6. Initialize the large TRX-state struct at `0x24013C0C`
   (`DAT_08022750`, in `.bss`): many field writes (mode, band, filter,
   drive, etc.).
7. **PA bias (Idd) auto-calibration** — strings `Prepare to adjust drive
   Idd`, `… final 1 Idd`, `… final 2 Idd`; checks external supply `Vext`
   is within 11–15 V first (`[ERR] Vext = %f is to low` / high). Sets
   bias via `FUN_08045088(channel, value)` (SPI2 10-bit DAC, clamped to
   1023) with channel 2 = driver, 8 = final 1, 7 = final 2; targets
   static Idd + 0.5 A / + 0.9 A, ±0.1 A (see peripherals.md, SPI2).
   HIGH CONFIDENCE.
8. `Init Radio Server`, TIM5 start (`[OK] Start TIM5`), audio processor
   init (`FUN_08033334`), etc.
9. Enter the superloop.

## Superloop (periodic dispatch)

Time base: `FUN_080277EC` = `HAL_GetTick`/millis, `FUN_080277F8(ms)` =
`HAL_Delay` (HIGH CONFIDENCE from usage). Each iteration:

- Refresh **IWDG** (`*(0x58004800) = 0xAAAA`, `IWDG_KR` key). VERIFIED.
- Poll serial for a line (`FUN_08041858(&ch)`, CR/LF terminates).
- 1000 ms cadence block (guarded by `tick - last >= 1000`): status /
  telemetry push (`FUN_0803B474`, `FUN_08021EB0`).
- ~2 ms cadence inner loop (`FUN_0803AD78` until `tick - mark >= 2`).
- Mode check `FUN_08048FA4()` (== 1 selects an alternate service path).
- Network/CI-V/streaming servicing (`FUN_0804AF68`, `FUN_0804B184`,
  `FUN_08041EF4`, `FUN_0803EC3C`, `FUN_08041358`).

## Clock / tick init — `FUN_08027774`

Evidence: `clock_init_08027774.txt`. Calls `FUN_080289A4(3)`, computes
the core/bus clocks by reading `RCC->CFGR` prescaler fields and indexing
a shift table (CMSIS `AHB/APBPrescTable` pattern), stores
`SystemCoreClock`-style globals, then configures SysTick
(`FUN_08027728(0xF)`, returns 1 on failure) and `FUN_080233E0`.

This is tick/`SystemCoreClockUpdate` setup, **not** the PLL bring-up —
by the time it runs the clock is already selected. The PLL bring-up is
`FUN_080222f0` (next section).

## Clock configuration — `FUN_080222f0` (SystemClock_Config), VERIFIED

`main` calls it before the tick setup. It runs in this order:
1. **Supply:** `FUN_0802c208` with value `0x2E`, the SMPS 2.5 V output
   feeding external loads and the LDO.
2. **Voltage scaling:** VOS = 00 in `PWR_D3CR`. On STM32H72x/H73x that
   is Scale 0, with no SYSCFG overdrive.
3. **Oscillators and PLL:** HAL_RCC_OscConfig (`FUN_0802c538`).
4. **Bus clocks:** HAL_RCC_ClockConfig (`FUN_0802cba0`), flash latency
   3 wait states.

| Item | Setting | Result |
| --- | --- | --- |
| HSE | on, crystal (not bypass); built for 25 MHz (HSE_VALUE) | 25 MHz |
| LSI | on | RTC clock |
| PLL1 | from HSE, M=2 N=44 P=1 Q=2 R=2, input range 8–16 MHz, wide VCO | VCO 550 MHz; P 550, Q 275, R 275 MHz |
| SYSCLK / CPU | PLL1P, D1CPRE /1 | **550 MHz** |
| HCLK (AXI/AHB) | HPRE /2 | **275 MHz** |
| PCLK1/2/3/4 | all /2 | **137.5 MHz** (timer clocks 275 MHz) |
| PLL2 | from HSE, M=2 N=16 P=Q=R=2 | VCO 200 MHz; 100 MHz outputs (ADC only) |
| PLL3 | not configured | — |

Peripheral kernel clocks, set through HAL_RCCEx_PeriphCLKConfig
(`FUN_0802d15c`):

| Kernel clock | Source | Rate | Set in |
| --- | --- | --- | --- |
| SPI6 (CH394) | PCLK4 | 137.5 MHz, so SCK at /8 ≈ **17.19 MHz** | `FUN_0802317c` |
| SPI1/2/3 (shared mux) | **I2S_CKIN pin** (mux value 3) | the firmware assumes 12.288 MHz | `FUN_0802317c`, `FUN_08021ccc` |
| ADC | PLL2P | 100 MHz, before the ADC's own prescaler | `FUN_08020f44` |
| I2C1/2/3 | PCLK1 | 137.5 MHz | `FUN_08021a00` |
| USART1/6 | PCLK2 | 137.5 MHz | `FUN_08024218` |
| USART2/3/4/5/7/8 | PCLK1 | 137.5 MHz | `FUN_08024218` |
| RTC | LSI | ~32 kHz | `FUN_08023008` |
| FMC, USB | never configured (reset defaults) | — | — |

The 12.288 MHz value is the constant that HAL_RCCEx_GetPeriphCLKFreq
(`FUN_0802e320`) returns for the external-pin source. 12.288 MHz /
3.072 MHz gives the I²S3 bit-clock divider of exactly 4 (48 kHz ×
64 bit). The same 12.288 MHz / 48 kHz pair is passed to the audio-codec
init (`FUN_0804a65c`). The pin clock is 245.76 MHz / 20, so it plausibly
comes from the VersaClock 6 output through the FPGA (HYPOTHESIS; see
`peripherals.md`).

Open: the 550 MHz clock needs the CPU-frequency-boost option byte on
H72x/H73x. The firmware never programs option bytes, so the byte was
either set in production or the part runs above the default 520 MHz
limit.

**Why this needed the firmware:** PLL dividers, prescalers, the supply
mode and the kernel-clock muxes are runtime register values. The
firmware is also the only source for the HSE_VALUE and I2S_CKIN
constants it was built with. Values are in
`analysis/clocks/clock_config.csv`.

## Named helpers (HIGH CONFIDENCE, not yet renamed in Ghidra)

| Address | Proposed | Basis |
| --- | --- | --- |
| `FUN_080277EC` | `HAL_GetTick` | ms counter, compared for cadences |
| `FUN_080277F8` | `HAL_Delay` | `(1000)`, `(100)`, `(10)` delays |
| `FUN_08053B2C` / `FUN_08053A4C` | console `log`/`logf` | printf-style with `[OK]/[ERR]` strings |
| `FUN_08045088` | `pa_set_bias(ch,val)` | PA Idd cal, 10/12-bit DAC values |
| `FUN_08041858` | `console_getchar` | returns 1 + char, CR/LF handling |

## Unknowns

- Identify the ~26 subsystem init functions (step 5).
- Locate PLL / SystemClock_Config and the resulting SYSCLK.
- Decode the TRX-state struct layout at `0x24013C0C`.
- CH394 Ethernet / CI-V / "WFV" streaming internals (Phase 5+).

## Interrupt paths — VERIFIED

Each vector stub calls the HAL handler and then the user code directly
(the HAL period-elapsed callbacks are empty).

| IRQ | Path |
| --- | --- |
| 3 | bootloader jump `FUN_0802200c`, then the RTC wake-up HAL handler |
| 9 / 10 / 23 / 40 | HAL EXTI, pins 3 / 4 / 6 / 10+13 → callback `FUN_08023ab4` (FPGA sample routine, CH394 INT flags, PTT, CW contacts) |
| 11 / 16 | HAL DMA on the I²S3 RX/TX DMA handles; `i2s3_stream_start` installs the half/complete/error callbacks |
| 15 | HAL DMA for USART2 TX; the user TX-complete callback is `FUN_08049638` |
| 18 | HAL ADC |
| 38 | HAL UART (USART2) |
| 47 | inline filtering of the seven ADC samples for the meters, then HAL DMA |
| 50 | HAL TIM, then the DSP scheduler (TX block `FUN_08034b88` / RX block `FUN_08033610`) |
| 54 | HAL DAC + HAL TIM, then the 100 Hz housekeeping cycle |
| 55 | HAL TIM, the 1 kHz service, conditionally the FFT, then the SLIP status frames |
| 68 | HAL DMA on the unused DMA2 Stream5 handle |
| 86 | HAL SPI (SPI6) |
| 118 | HAL TIM, then wide-span decimation and the wfview TX-audio ring step |
| 129 / 130 | HAL DMA on the BDMA channel handles (SPI6) |

## Protections and limits (V1.0.1) — VERIFIED unless noted

The firmware has almost no runtime RF protection.

**At boot only.** Vext (11–15 V) and the static drain current (≤ 0.1 A
with all bias off) are checked once. Failing either only skips the PA
bias trim; TX is not inhibited.

**Never.** No code inhibits TX on SWR, PA temperature, Vext or Idd. The
only consumers of those measurements are:
- the fan control;
- the ATU;
- the console;
- the `0x03` frame.

This was established by an exhaustive literal scan for the meter
struct.

**Fan (fan role HYPOTHESIS).** The PA temperature drives a fan level,
SPI2 DAC channel 3 = 10·T − 50 above 35 °C, off at ≤ 30 °C, updated
about once per second.

**TX inhibits.** TX is inhibited only by:
- the global TX enable;
- the band table (see "TX band enforcement");
- loss of the Control link (about 1000 main-loop passes, which drops
  the built-in PTT);
- the CW trainer mode (keys without RF).

A frequency change into a denied range during TX, or switching the
global TX enable off, forces RX. VFO select is refused while
transmitting.

**ATU limits.**
- Tunes with a 10 W CW carrier and refuses f > 54 MHz.
- Waits 100 ms before searching and 25 ms per step.
- Aborts after an 8 s guard or when the match stays above g = 8.0.
- Fails its self-test below 0.5 W forward.

**Power fold-back (HIGH CONFIDENCE).** In AM/SAM the power reference
(DAC channel 6) is computed from P/4. The drive code is clamped to
300–1000, and every DAC value to 1023.

Values are in `analysis/flow/protections.csv`.

**Why this needed the firmware:** which conditions are checked, and
which the firmware ignores, is software policy that no schematic shows.

## TX band enforcement — VERIFIED

**Band table.** The calibration block holds an 11-entry TX band table
at offset `0x072` ({u64 start Hz, u64 end Hz, u32 enable}, 20 B each).
The defaults cover 160 m to 6 m, including 5.332–5.405 MHz, all
enabled (`main_unit/analysis/protocol/cal02_band_defaults.csv`).

**Check.** `FUN_0803d198` denies TX when:
- the global TX enable is off, or
- the frequency is outside the hard window of 1.2–54.0 MHz.

Inside the window it allows TX when any of these holds:
- the SWR-scan PTT is active;
- a factory override in the calibration block is set (cleared at boot
  in V1.0.1, so it is not active in normal use);
- the frequency lies inside an enabled table entry (inclusive edges).

**Applying the result.**
- The frequency setter `FUN_0803d658` stores the result in TRX+0x228
  on every frequency change.
- Keying while denied enters the TX state and logs a message, but
  applies no bias and switches no T/R lines (the SWR scan overrides
  this).
- A split TX on a denied frequency is refused.
- A frequency change into a denied range during TX forces RX.

**Who can change the table.** The `0x01` settings image cannot. Only a
`0x02` set frame (factory tool) can, and that path does not write the
EEPROM.

**BandMap.** The 1920-byte "BandMap" size printed at boot belongs to a
type that no Main code allocates, loads or sends. It is probably the
Control Unit band stack (HYPOTHESIS).
