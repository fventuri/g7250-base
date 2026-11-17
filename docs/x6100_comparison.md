# G7250 compared with the X6100 (and G90)

Status: X6100 and G90 parts DONE, each limited to its source (below). The G7250 side comes from this repo's own findings.
The X6100 side comes from two places:
- the X6100 facts already recorded in these docs (the tooling and
  method were ported from an X6100 BASE project);
- the **public OpenX6X00 project** (GitHub, Guru-RF/OpenX6X00), whose
  Linux GUI drives the X6100 base board through a control library.

Only interface facts visible in that public source are used, and no
code is taken from it. There is **no G90 material** in this repo or its
sources. The G90 comparison below therefore uses only Radioddity's
public document "G90 CAT control and digital modes" v1.0 (its CI-V
table and connection notes), not G90 firmware.

## Architecture

| Aspect | X6100 | G7250 |
| --- | --- | --- |
| Host / UI processor | Linux SoC (Allwinner R16) running the GUI | STM32H743 "Control Unit" running a bare-metal emWin GUI |
| Baseband processor | STM32F427 "BASE" | STM32H725/H735 "Main Unit" (550 MHz) |
| RF front end | codec-based I/Q (CS4272 + TLV320AIC3204 on I2C) | an FPGA delivering 24-bit I/Q over a bit-banged GPIO bus; an AIC3204 only for audio |
| Clock generator | VersaClock 5P49V60 at 0x6A | VersaClock 6 (5P49V6965) at 0x68, fallback 0x6A |
| Power | battery with a MAX17205 fuel gauge; the control library has a charger setting | mains only; AXP223 PMIC, no battery (the X6100's Linux host also has an AXP223, per its public device tree) |
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

## Field-by-field: X6100 base registers → G7250 `0x01` image

**Source.** The X6100 register list is the public enum of the X6100
control library (GitHub gdyuldin/X6100Control). It has 47 I2C register
slots (indices 0–55, with gaps), each carrying a 32-bit word. The
G7250 offsets are from `main_unit/analysis/protocol/cmd01_fields.csv`
and `cmd01_vfo_record.csv`.

| X6100 register (index) | Content | G7250 equivalent |
| --- | --- | --- |
| vfoa_ham_band (0) … vfoa_agc (5), vfob_* (6–11) | per-VFO band, frequency, ATT, PRE, mode, AGC | VFO records at `0x024` / `0x04C` (frequency u64, mode +0x18, ATT +0x25, PRE +0x26, AGC +0x20/+0x23); no band id |
| sple_atue_trx (12) | split, voice-record, SWR-scan, ATU enable, ATU tune, modem TX, calibration TX, power-off, internal PTT bits | split `0x0A4`, ATU switch `0x0AC`, PTT-source bits in `0x15E` (built-in PTT, CW serial, tune, SWR scan, CI-V); power-off travels the other way (`0x03` flags bit 2) |
| vi_vm (13) | selected VFO, band id | selected VFO `0x098` |
| rxvol (14) | RX volume | AF gain stays on Control (applied in its own codec) |
| rfg_txpwr (15) | RF gain, TX power, FFT span | RF gain `0x07B`, TX power `0x154` (f32 W), span index `0x088` |
| atu_network (17) | ATU L/C/style | held on Main only (EEPROM ATU table, `docs/atu.md`); not in the image |
| flow_fm_emp (18) | flow format, FM emphasis | none |
| dac_adc_offsets (19) | gain offsets | none (Main-internal) |
| ling_loutg_imicg_hmicg (20) | line-in, line-out, internal and handheld mic gain | line-in `0x0C8`, line-out `0x100`, one mic gain `0x0C4` |
| micsel_pttmode_chge_spmode_auxiqgen_sqlthr (21) | mic select, PTT mode, charger, speaker mode, aux IQ, squelch threshold | global squelch `0x15D`; the rest has no counterpart |
| voxg_voxag_voxdly_voxe (22) | VOX gain, anti-VOX, delay, on | VOX threshold `0x117`, timeout `0x0EA`, switch `0x11F`; no anti-VOX |
| nrthr_nbw_nbthr_nre_nbe (23) | NR level, NB width/level, NR/NB enable | NR level `0x0F2`, NB level `0x0F7`, NB switch `0x11B`; NR type per VFO (+0x1C); no NB width |
| dnfcnt_dnfwidth_dnfe (24) | notch centre/width/enable | notch centre (VFO +0x1A), manual/auto notch (+0x1E/+0x1F); no width |
| cmplevel_cmpe (25) | compressor level (off, 1:2, 1:4, 1:8), enable | compressor switch `0x170`, ratio index `0x171` |
| agcknee/agcslope/agchang (27), agctime (28) | AGC shape | none (AGC is a per-VFO mode only) |
| monilevel (29) | monitor level | `0x0FF` |
| ks_km_kimb_cwtone_cwvol_cwtrain (33) | key speed, key mode, iambic, CW tone, CW volume, trainer | `0x12E`, `0x134/0x137/0x139`, `0x138`, `0x128`, `0x15A`, `0x159` |
| qsktime_kr (34) | QSK time, key ratio | `0x12A`, `0x124` |
| if_shift (35), cw_peak_cessb (36) | IF shift, CW peak filter, CESSB | none |
| tx_filter (38) | TX filter low/high | TX filter edges per mode `0x0DA`–`0x0E6` |
| biasdrive_biasfinal (41) | PA bias values | calibration block `0x02` (`0x14E`–`0x152`), not the settings image |
| rit (42), xit (43) | RIT/XIT | `0x074` / `0x076` plus switches `0x0A2` / `0x0A3` |
| filter1/2_low/high (44–47) | RX filter edges | RX filter half-words `0x0D4`–`0x0E8` per mode |
| rphscmp, rmagcmp (48–49), txiofs, txqofs (50–51) | RX/TX I/Q phase, magnitude and offset trims | none (no I/Q trim in the image) |
| pwrsync (53) | supply-switching sync | none |

**Matching enums.**
- **Key mode.** The X6100 key mode (manual, auto-left, auto-right) has
  the same 0/1/2 codes as the G7250 key type (straight, paddle,
  reversed). The G7250 spreads it over three bytes on the wire.
- **Iambic A/B** use the same codes.
- **Compressor.** The X6100 compressor levels (off, 1:2, 1:4, 1:8)
  correspond to the G7250 switch plus a four-step ratio index.
- **AGC differs.** On the X6100 it is off/slow/fast/auto; on the G7250
  it is an on/off byte plus a speed code, mapped by CI-V as FAST/MID/SLOW.

**What the comparison shows.** The G7250 `0x01` image carries
essentially the X6100 base register set, flattened into fixed offsets.
Several X6100 DSP and trim registers are missing, while network, CW
decoder and RTTY fields are new. This is consistent with Xiegu evolving
the X6100 base protocol into the G7250 settings image (HYPOTHESIS).

## G90 (from its published CI-V table)

**Architecture.** Like the G7250, the G90 is split into a base unit and
a display unit, each with its own firmware update. The published guide
lists separate updates for both units. CAT runs at 19 200 baud on the
display unit's serial port, and firmware updates at 115 200 baud.

**CI-V.** The G90 implements a subset of Icom CI-V and answers several
addresses (default 0x70). The G7250 has two parsers (`docs/civ.md`):
- the **Control Unit USART1 parser**, which closely matches the G90;
- the **Main Unit wfview parser**, an IC-7300 emulation.

| Command | G90 (published) | G7250 Control parser | G7250 Main (wfview) |
| --- | --- | --- | --- |
| addressing | answers several addresses | no address filter; 0x19 echoes the caller's address | 0xA0 or broadcast only |
| 00 / 05 | set frequency | 05 sets frequency | 00 sets frequency; 05 selects the VFO (quirk) |
| 01 / 06 | set mode | 06 sets mode | 06 sets mode |
| 02 | get band edges | fixed band-edge reply | not handled |
| 03 / 04 | get frequency / mode | same | same |
| 07 | 00 VFO A, 01 VFO B, B0 swap | **same three** | adds A0 copy A→B, B1 copy |
| 0F | split off/on | same | same |
| 11 | toggle/get ATT | read (0x20 = on) / set | same as Control |
| 14 | 01 AF, 03 SQL, 09 CW tone, 0A power, 0C key speed; others read 255 | 01 02 03 06 0A 0B 0C 12; others read 0 | full set incl. NR, mic, compressor, break-in, NB, monitor, VOX |
| 15 | 01 SQL, 02 S, 11 Po, 12 SWR | 02 S, 12 SWR, 15 Vd | 02 S, 11 Po, 12 SWR, 13 ALC, 15 Vd, 16 Id |
| 16 | 02 PRE, 12 AGC, 22 NB, 44 COMP, 50 dial lock | 02 PRE, 22 NB, 40–50 subset | 02, 22, 40–47 functions |
| 1C | 00 PTT, 01 ATU off/on/tune | 00 PTT | 00 PTT, 01 ATU off/on/tune |
| 19, 1A, 1D, 25, 26 | not listed | 19, 1A (filter, AGC), 1D vendor, 25, 26 | 19, 1A, 25, 26, 27 scope |

**Mode codes on the wire.** All three use the Icom codes (00 LSB, 01 USB,
02 AM, 03 CW, 07 CWR). The G7250 adds RTTY and FM codes.

**Conclusion (HYPOTHESIS).** The G7250 Control CI-V parser looks like
the G90 parser, extended with more levels, meters and the 0x25/0x26
VFO commands: same VFO sub-commands, same ATT/PTT/ATU forms, the same
"answer any address" behaviour. The Main wfview parser is a separate
IC-7300 emulation.

**Limits.** The table compares the G7250 firmware with the G90's
*published* command list, not with G90 firmware. G90 internals (MCUs,
the base protocol between its two units) are not covered by any source
available here.

## Timing and robustness

- **X6100 (from the public GUI code).** Base writes can fail and are
  re-sent by the host. The host backs off and pulses the baseband reset
  when the base does not answer at start-up.
- **G7250.** Settings are idempotent full images. Main has a 2–3 s
  controller timeout that only drops PTT/key/tune requests. Control has
  no Main timeout (`docs/protocol.md`, Link state machine).

## Open

- G90: internals (MCUs, base↔display protocol) need G90 firmware analysis,
  which is not available here.

**Why this needed the firmware:** the G7250 side of every row (image
layout, mode codes, timing) exists only in the G7250 firmware.
