# Main Unit — DSP pipeline (PARTIAL)

Status: the structure, data paths, formats and scheduling are VERIFIED
unless noted. Several individual stages are only MEDIUM CONFIDENCE or
HYPOTHESIS. Function list: `analysis/dsp/dsp_functions.csv`.

## Data paths

- **RF I/Q from the FPGA.** The FPGA bit-banged bus on PE0–PE9 (see
  `peripherals.md`, FPGA bus) carries 24-bit signed I and Q.
  - The FPGA sample interrupt (PE10 / EXTI10, `FUN_08039078`) reads
    1, 2, 4 or 8 complex samples, depending on the span setting
    (settings `0x088`, or `0x08C` in NFM/WFM).
  - The samples go into a 192-sample ping-pong for the audio DSP and a
    256-sample ping-pong for the FFT/scope.
  - TX samples go back to the FPGA from a 2×192-sample ring
    (`0x2400E9F0` / `0x2400EFF0`).
  - The interrupt rate is not visible in the firmware. 48 kHz, giving
    384/192/96/48 kS/s, is a HYPOTHESIS, consistent with the
    decimate-by-8/4/2/1 path `FUN_08033390`.
- **Audio through the AIC3204 on I²S3.** 48 kHz, 32-bit stereo, in
  4 ms DMA halves of 192 frames.
- **Block size and scheduling.** All baseband DSP runs on
  **192-sample 32-bit float blocks**. The TIM5 interrupt (`FUN_080239c8`)
  runs the TX routine `FUN_08034b88` while PTT, VOX or tune is active,
  and the RX routine `FUN_08033610` otherwise. The TIM6 interrupt
  (`FUN_080239e0`) runs housekeeping, including underrun checks and PTT
  handling. The RX routine is timed with the DWT cycle counter.
- **Mode codes** (VFO record byte 0x18): 0 LSB, 1 L-D, 2 USB, 3 U-D,
  4 CW, 5 CWR, 6 AM, 7 SAM, 8 NFM, 9 WFM, 10 IQ, 11 LBK (loopback,
  skips the FPGA bus), 12 RTTY.

## RX chain (`FUN_08033610`)

1. **Input.** The FPGA I/Q block is copied into working buffers; the
   codec input is kept for a line-monitor mix.
2. **IQ balance (HYPOTHESIS).** A running correlation between I and Q
   looks like an I/Q phase-imbalance estimate.
3. **LAN IQ tap.** The block is converted to int16 for the HDSDR
   service (`network.md`).
4. **IF gain and S-meter (MEDIUM).** IF gain with overload detection,
   then the S-meter.
5. **Demodulation per mode:**
   - **SSB/data/RTTY:** the phasing method, using a **201-tap Hilbert
     FIR** on one branch and a 201-tap matched delay FIR on the other,
     subtracted for LSB and added for USB (VERIFIED).
   - **CW:** complex band-pass and a pitch shift (MEDIUM).
   - **AM:** envelope with a DC blocker (MEDIUM).
   - **SAM:** a carrier-tracking loop (MEDIUM).
   - **FM:** FM squelch with filters; the discriminator itself is not
     pinned down.
6. **Optional stages:**
   - noise blanker (MEDIUM);
   - adaptive auto-notch (HYPOTHESIS);
   - squelch;
   - a gain-control stage (AGC? HYPOTHESIS).
7. **Noise reduction (MEDIUM).** The audio is resampled to 16 kHz in
   256-sample frames, passed through a suppressor engine whose level is
   set from 1–100, then resampled back to 48 kHz.
8. **RX equaliser.** Five-band biquad EQ, designed at runtime.
9. **Output.**
   - the wfview RX audio tap;
   - AF volume;
   - the line-monitor mix and beeps;
   - an MDMA copy into the I²S3 TX buffer.

## TX chain (`FUN_08034b88`)

1. **Input.** One channel of the I²S3 receive stream (the mic or line
   input), or the wfview TX audio.
2. **Audio shaping.**
   - five-band TX EQ;
   - TX HPF/LPF biquads;
   - DC blockers (one-pole);
   - VOX and envelope tracking;
   - compressor/soft clipper with a post-clip filter (MEDIUM).
3. **Modulation per mode:**
   - **SSB/RTTY:** phasing, with a second Hilbert/delay FIR pair;
   - **CW:** keyer envelope, with the dot length from the WPM setting;
   - **AM/SAM:** carrier × (1 + m·audio);
   - **FM:** phase accumulation, then cos/sin.
4. **Drive and ALC (MEDIUM).** A per-band drive gain selected from
   frequency thresholds, a smoothed ramp-up and a fixed scale. The ALC
   feedback loop is not yet pinned down.
5. **Monitor and sidetone.** The TX monitor or the CW sidetone goes to
   the I²S3 TX buffer.
6. **Output.** A cache clean, then an MDMA copy into the FPGA TX ring.

## Filter implementation

- **Biquads.** Cascades in transposed direct form II (5 coefficients
  and 2 state values per stage). They follow CMSIS-DSP-shaped
  primitives; see the CSV for FIR, FIR decimator/interpolator and
  vector helpers.
- **Runtime design (HIGH CONFIDENCE).** The coefficients are designed at
  runtime in `FUN_08032020` from the filter-edge settings, with the EQ
  peaking design in `FUN_08031cdc`, and are recomputed when the mode or
  filter changes.
- **Fixed tables.** Only the 201-tap SSB Hilbert and delay tables are
  fixed in flash, at `0x08079FE0` and `0x08079CBC`.

**Fixed SSB FIR pair (VERIFIED numerically).**
- `0x08079FE0` holds a 201-tap antisymmetric FIR with every other tap
  zero: a Hilbert transformer.
- `0x08079CBC` holds a 201-tap symmetric FIR whose centre tap is close
  to 1: a delay FIR.
- Both have a linear-phase delay of 100 samples, and their phase
  difference is +90° at all frequencies.
- Assuming 48 kHz (HYPOTHESIS), the Hilbert magnitude is about −0.45 dB
  at 300 Hz and flat within 0.04 dB from about 1 kHz to 20 kHz.

Reproduce with `tools/filter_response.py` (FIR mode on the image,
address, 201 taps). The X6100 biquad checker was removed, because the
G7250 biquads are designed at runtime.

**Why this needed the firmware:** no public document describes the
I/Q-vs-audio split, the sample formats, the block scheduling, the LAN
taps or the filter structures. They exist only in the code.
