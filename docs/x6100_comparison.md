# G7250 compared with the X6100 (and G90)

Status: PARTIAL. The G7250 side comes from this repo's own findings.
The X6100 side comes from two places:
- the X6100 facts already recorded in these docs (the tooling and
  method were ported from an X6100 BASE project);
- the **public OpenX6X00 project** (GitHub, Guru-RF/OpenX6X00), whose
  Linux GUI drives the X6100 base board through a control library.

Only interface facts visible in that public source are used, and no
code is taken from it. There is **no G90 material** in this repo or its
sources, so no G90 comparison is possible here (BLOCKED).

## Architecture

| Aspect | X6100 | G7250 |
| --- | --- | --- |
| Host / UI processor | Linux SoC (Allwinner R16) running the GUI | STM32H743 "Control Unit" running a bare-metal emWin GUI |
| Baseband processor | STM32F427 "BASE" | STM32H725/H735 "Main Unit" (550 MHz) |
| RF front end | codec-based I/Q (CS4272 + TLV320AIC3204 on I2C) | an FPGA delivering 24-bit I/Q over a bit-banged GPIO bus; an AIC3204 only for audio |
| Clock generator | VersaClock 5P49V60 at 0x6A | VersaClock 6 (5P49V6965) at 0x68, fallback 0x6A |
| Power | battery with a MAX17205 fuel gauge; the control library has a charger setting | mains only; AXP223 PMIC, no battery |
| Networking | via the Linux host | CH394 Ethernet on the Main Unit (HDSDR and wfview modes) |

The G7250 keeps the X6100's split between UI and baseband, but replaces
the Linux host with a second STM32. RF sampling moves into an FPGA.

## Host ↔ baseband interface

| Aspect | X6100 (OpenX6X00 control library) | G7250 (SLIP, `docs/protocol.md`) |
| --- | --- | --- |
| Settings transport | one command per setting: a register id plus a 32-bit argument; the library keeps a register copy, and a failed write must be retried by the caller | one **424-byte settings image**, sent every 20 ms over SLIP/USART2, diff-applied by Main; no per-field acknowledge |
| Baseband → host data | a separate "flow" stream (spectrum and samples, FP32 or BF16 formats) | SLIP `0x03`: a 512-byte spectrum plus a meter/status tail, at the FFT rate |
| Network-originated changes | handled on the Linux host | SLIP `0x08`, a sequenced and acknowledged state push |
| Baseband version | a version query used to gate features | SLIP `0x06` slave info: version strings |
| Baseband reset | a host GPIO pulses the baseband reset when the base stops answering | no reset line; Main just stops seeing `0x01` and reports the controller offline after about 2–3 s |
| CW keying from the host | a host GPIO "morse key" line | the Control Unit pulls PE3/PE4 low for CW memories |

The G7250 interface is a full-state image rather than a command set.
This removes the X6100's failure mode of losing a single write, at the
cost of 21 kB/s of constant traffic.

## Mode enumeration

| Code | X6100 | G7250 |
| ---: | --- | --- |
| 0 | LSB | LSB |
| 1 | LSB-DIG | L-D |
| 2 | USB | USB |
| 3 | USB-DIG | U-D |
| 4 | CW | CW |
| 5 | CWR | CWR |
| 6 | AM | AM |
| 7 | NFM | **SAM** |
| 8 | — | NFM |
| 9 | — | WFM |
| 10–12 | — | IQ, LBK (loopback), RTTY |

Codes 0–6 are identical. The G7250 inserts SAM at 7 and appends NFM,
WFM, IQ, loopback and RTTY. A port between the two needs a translation
only from code 7 upward (VERIFIED for the G7250 table; the X6100 side is
from the public enum).

## Feature settings

**Present on both**, as X6100 control calls and G7250 `0x01` fields:
- VFO frequency and mode, split;
- PRE, ATT, AGC, RF gain, squelch;
- NB/NR levels, notch, VOX (gain/delay);
- mic gain, line in/out, monitor;
- compressor;
- TX filter edges, TX power;
- CW speed, ratio, tone, mode, iambic type, QSK time, trainer;
- ATU tune;
- SWR scan;
- PTT.

**X6100 only** (no counterpart in the G7250 `0x01` image or the Main
DSP map):
- CESSB;
- IF shift;
- CW peak filter;
- separate compressor threshold/makeup;
- FM emphasis;
- separate internal/handheld mic selection;
- TX I/Q offset trims;
- the battery charger.

**G7250 only:**
- wfview/HDSDR network settings and credentials;
- antenna select;
- RTTY and WFM modes;
- SAM;
- a CW decoder on the Control Unit;
- band-limit tables in the calibration EEPROM block.

## Timing and robustness

- **X6100 (from the public GUI code).** Base writes can fail and are
  re-sent by the host. The host backs off and pulses the baseband reset
  when the base does not answer at start-up.
- **G7250.** Settings are idempotent full images. Main has a 2–3 s
  controller timeout that only drops PTT/key/tune requests. Control has
  no Main timeout (`docs/protocol.md`, Link state machine).

## Open

- A field-by-field comparison of the X6100 base register map with the
  G7250 settings image needs the X6100 control library's register
  list. Only the call names are visible in OpenX6X00.
- G90: no firmware analysis available.

**Why this needed the firmware:** the G7250 side of every row (image
layout, mode codes, timing) exists only in the G7250 firmware.
