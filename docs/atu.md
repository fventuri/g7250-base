# Built-in ATU (Main Unit)

Status: VERIFIED unless noted. Constants: `main_unit/analysis/peripherals/atu_engine.csv`.

## Hardware interface (SPI1 latches)

| Latch | CS | Content |
| --- | --- | --- |
| L bank | PG2 | 8-bit L value, bit order kept (`FUN_08044e34`) |
| C bank | PG5 | 8-bit C value, bit order mirrored (`FUN_08044dc0`) |
| Control | PD13 | bits 0–1 network style (one-hot pair); bits 2–3 ATU in line (set) / bypass (clear); bits 4–5 antenna select (MEDIUM) |

The EEPROM slot bytes are L, C and S (network style); see
`main_unit/docs/memory_map.md`.

## Supervisor (`FUN_08041358`, each main-loop pass)

**Recall.** On a change of frequency slot (100 kHz bins) or antenna,
the slot is recalled. An empty slot means bypass. Otherwise L, C and S
are applied, and the ATU is put in line only if the ATU switch (`0x0AC`)
is on.

**Tune.** Requested through `0x01` byte `0x15E` bit 5.
1. The request is refused above 54 MHz.
2. The ATU saves the mode and power, forces CW and 10 W, puts the ATU
   in line and clears the banks.
3. It enters TX after 10 ms and starts the engine 100 ms later.
4. It aborts on a frequency, antenna or TX change.
5. It returns to RX 200 ms after the end and restores mode and power.

**Result.** On success S/L/C are written into the slot and the EEPROM
dirty flag is set; otherwise the old slot is recalled. Result codes:
1 ok, 3 fail, 4 aborted.

**Seed.** The first non-empty neighbour slot in the order +1, −1, +2,
−2. The current slot itself is never the seed.

## Search engine (`FUN_08042d34`, non-blocking state machine)

**Per point.**
- relay settle of 5 ms (8 ms in fine/final, 10–300 ms at start);
- median of 3 merit samples (5 for confirmations and the final point);
- 25 ms timeout per sample;
- overall guard of 8 s.

**Sequence.**
1. **Zero:** L = C = 0, style 0, then settle.
2. **Self-test:** forward power must be ≥ 0.5 W, and switching L or C
   fully in must move the merit g by ≥ 0.2.
3. **Warm start:** the seed is accepted if g ≤ 2.0, which skips the
   coarse search.
4. **Coarse:**
   - The style is chosen by probing L = 0x40, C = 0x80 under both
     styles.
   - Then a 10 × 10 grid over {0, 1, 2, 4, 8, 16, 32, 64, 128, 255} for
     L and C. An improvement must beat the best by 0.05, and up to
     three distinct candidates are kept.
   - The search exits early at g ≤ 1.5 (confirmed). It tries the other
     style if the best g > 2.0, and aborts if the best g > 8.0.
5. **Fine:** a hill-climb from each candidate, with steps 16/8/4/2/1,
   at most 40 evaluations per start, and improvement > 0.05.
6. **Carry probe:** L ± 2/4/8 with C re-optimised. An improvement
   restarts the fine search.
7. **Final:** success if g ≤ 3.0.

## Merit g — VERIFIED

g is the **raw block SWR** at meter block +0x20 (`0x24004D5C`). It is
computed in the ADC1 DMA interrupt (`FUN_080235e8`) at the end of every
block of 15 ADC sample sets:
1. it averages the forward and reflected detector values (2 × ADC
   counts, not watts);
2. it scales the reflected average by the per-frequency reverse gain and
   subtracts the leakage factor times forward (both set by
   `FUN_0803ec3c`);
3. it clamps the result to 0…0.999 × forward and divides by forward,
   which gives Γ;
4. g = (1+Γ)/(1−Γ), or 999.9 with no forward signal.

Unlike the displayed SWR, g is neither smoothed nor gated by the
signal-level and 20-block validity checks.

**Handshake.** For each sample the engine (`FUN_08042d34`) sets the
block-reset byte (+0x74), so the next block contains only post-settle
samples. It then waits for the block-done byte (+0x39) and clears it. A
block that does not arrive within 25 ms counts as 999.9.

## External tuner

No firmware handling of the TUNER TRG/RET connector was found
(MEDIUM CONFIDENCE).

**Why this needed the firmware:** latch roles, bit order, the grid,
step tables, thresholds and timing are software choices.
