# Main Unit — main() control flow

Function: `FUN_0802239C` (candidate `main`, HIGH CONFIDENCE).
Evidence: `main_unit/analysis/flow/main_decompile.txt`,
`clock_init_08027774.txt`, strings.

**Bare-metal, no RTOS.** `main()` runs init then an infinite superloop.
VERIFIED (the function never returns; ends in `do { … } while(true)`).

## Boot sequence (in order)

1. If in privileged mode, disable interrupts (`enableIRQinterrupts(0)`).
2. Early setup: `FUN_0804a7c0`, then buffer/clear helpers
   (`FUN_08053b3c/08053f64/08053fb6/08053ca4`).
3. **Enable Cortex-M7 I-cache then D-cache** via `SCB->CCR` (SCB base
   `0xE000ED00`): invalidate (`ICIALLU` @+0x250, `DCISW` set/way loop
   @+0x260), set `CCR.IC` (bit 17) and `CCR.DC` (bit 16), with DSB/ISB.
   VERIFIED.
4. `FUN_08027774` — tick / clock setup (see below).
5. ~26 subsystem init calls (`FUN_080222f0`, `FUN_08021470`, … through
   `FUN_08021830`) — not yet individually identified.
6. Initialize the large TRX-state struct at `0x24013C0C`
   (`DAT_08022750`, in `.bss`): many field writes (mode, band, filter,
   drive, etc.).
7. **PA bias (Idd) auto-calibration** — strings `Prepare to adjust drive
   Idd`, `… final 1 Idd`, `… final 2 Idd`; checks external supply `Vext`
   is within 11–15 V first (`[ERR] Vext = %f is to low` / high). Sets
   bias via `FUN_08045088(channel, value)` with channel 2 = driver,
   8 = final 1, 7 = final 2, iterating until measured Idd converges.
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
by the time it runs the clock is already selected. The actual
PLL/`SystemClock_Config` has not yet been located (SystemInit only
resets the clock tree). TODO.

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
