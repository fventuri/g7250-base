# Inter-MCU protocol (Main Unit ↔ Control Unit)

The two STM32H7 MCUs communicate over a USART using **SLIP framing**
(RFC 1055) with a trailing **CRC-16/ARC**. Both units share the same
code (identical SLIP/CRC primitives and error strings).

Status: framing, CRC, and primitives **VERIFIED** (decompiled +
disassembled). Command semantics **HIGH CONFIDENCE** (payload sizes
verified; meanings inferred). Header middle bytes **HYPOTHESIS**.

## Physical layer — VERIFIED

Both units use **USART2 on PD5 (TX) / PD6 (RX), alternate function 7**:
**460 800 baud, 8N1** (8 data bits, no parity, 1 stop bit). There is no
hardware flow control; oversampling is 16× and the hardware FIFO is
disabled after init. The kernel clock is PCLK1: 137.5 MHz on the Main
Unit and 120 MHz on the Control Unit.

| | Main Unit | Control Unit |
| --- | --- | --- |
| Handle init / MSP | `FUN_08024190` / `FUN_08024218` | `FUN_080232bc` / `FUN_08023344` |
| TX DMA | DMA1 Stream4, request 44, normal mode, high priority | DMA1 Stream2, request 44, normal mode, high priority |
| RX DMA | DMA1 Stream2, request 43, **circular**, low priority | DMA1 Stream3, request 43, **circular**, high priority |
| USART2 IRQ38 priority | 10 | 1 |

**Why this needed the firmware:** the CTRL cable is unlabelled. The
baud rate, pins and DMA assignment exist only in the init code.

## Transport

- USART with a **DMA circular RX buffer**: 1024 B (`0x400`) on the Main
  Unit, 4096 B (`0x1000`) on the Control Unit. The RX handler drains the
  ring using the DMA counter (`0x400/0x1000 − DMA_NDTR`), handling
  wraparound, and reassembles into a linear frame buffer (2048 B main /
  8192 B control) (VERIFIED).
- RX handlers:
  - Main Unit: `FUN_08049658`, polled from the superloop (VERIFIED).
  - Control Unit: `FUN_08034984`, called from the TIM13 period callback
    `FUN_080228cc`, so it runs in interrupt context (HIGH CONFIDENCE).
- **RX re-arm.** The receiver is re-armed only when it has made no
  progress for 100 polls and the overrun flag is set. That is about
  200 ms on Main and about 2 s on Control (HIGH CONFIDENCE).

## SLIP framing (RFC 1055) — VERIFIED

Encoder `FUN_0804a200`, decoder `FUN_0804a258` (Main Unit; Control Unit
has equivalents `…a200`→`FUN_08052c…`, `decode`→`FUN_08052be4`).

| Byte | Name | Encoded as |
| --- | --- | --- |
| `0xC0` | END | `0xDB 0xDC` (ESC, ESC_END) |
| `0xDB` | ESC | `0xDB 0xDD` (ESC, ESC_ESC) |
| other | — | unchanged |

- A frame is terminated by a single trailing `0xC0`. The encoder emits
  **no leading END**; the decoder skips empty frames, so stray leading
  `0xC0` bytes are tolerated.
- Decoder returns the decoded length, or `-1` on output overflow.

## Packet layout (decoded)

```
+--------+------------------------+-----------+
| type   |        payload         |  CRC-16   |
| 1 byte |        N bytes         |  2 bytes  |   (CRC is little-endian)
+--------+------------------------+-----------+
 \__________ CRC input ___________/
```

- **CRC-16/ARC**: poly `0x8005` (reflected `0xA001`), init `0x0000`,
  refin/refout = true, xorout `0x0000`. Table-driven:
  `crc = table[(crc ^ byte) & 0xFF] ^ (crc >> 8)`, seed 0.
  Functions: Main `FUN_0804ae3c` (table `0x0807F8B0`), Control
  `FUN_08052c44` (table `0x080C7360`). VERIFIED identical.
- CRC covers the whole decoded packet except the trailing 2 CRC bytes.
- Minimum decoded length: 5 B (Main) / 6 B (Control); shorter frames are
  logged as invalid, with the raw and decoded lengths.
- A CRC mismatch is logged with the computed and the received value.
- The first decoded byte is the **message type**; dispatch is a switch on
  it.
- **Frame layout.** Every frame is `[type][0x00][0x00]<payload><crc16>`.
  All six frame builders on both units write bytes 1–2 as zero, and
  neither receiver ever reads them (VERIFIED), so treat them as
  reserved. Sequencing, where it exists, lives inside the payload (type
  `0x08`).
- **Error handling.** Unknown types are silently ignored. Only the Main
  `0x02` handler checks lengths; every other handler copies a fixed
  size without checking.

## Payload layouts

Message identities (VERIFIED from the handlers' debug strings):

- **`0x01` = remote-control settings/state** pushed to the Main Unit.
  Copied to a 424-B struct at `0x24018F9C`; consumed each superloop by
  `FUN_08041EF4` (diffs each field vs. a working copy and logs changes) (VERIFIED).
- **`0x02` = calibration data.** 358-B block at `0x24013AA4`. It ends two
  bytes before the TRX-state struct (`0x24013C0C`), but it is a separate
  block, with its own loader, EEPROM location and checksum (VERIFIED).
- **`0x06` = "slave info"** (the handler logs a debug line). 104-B block at
  `0x24018F30` (VERIFIED).

The Main Unit emulates an **Icom-style network radio for wfview** — the
settings block carries the wfview username and password and the IPv4
configuration, and Main logs when the remote controller goes offline.

### `0x01` settings block (424 B)

**What it is.** The `0x01` payload is the radio's **settings image**.
It has the same layout as the first 0x1A8 bytes of the Main TRX struct
(`0x24013C0C`), which Main also loads from backup SRAM or the EEPROM
(see `main_unit/docs/memory_map.md`) (HIGH CONFIDENCE).

**Producers and consumers.** Control fills the payload in
`FUN_0803e76c` from its UI state, with byte 0 = 0xAA; Main ignores
byte 0. Main applies the payload in `FUN_08041EF4` (VERIFIED).

**Special handling:**
- The VFO block (`0x024`–`0x073`, two 40-byte VFO records) is applied
  only when no network client controls the radio.
- Squelch travels as 0–100, and Main converts it to −100…−50 dB.
- Some fields that Control sends are ignored by Main.
- Control V1.0.1 never writes flags 2, the extra EQ bytes, the global
  squelch threshold or the VFO AGC byte, so they keep their init values.

**Files.**
- Full field map: `main_unit/analysis/protocol/cmd01_fields.csv`.
- VFO record: `cmd01_vfo_record.csv`. Mode codes: 0 LSB, 1 L-D, 2 USB,
  3 U-D, 4 CW, 5 CWR, 6 AM, 7 SAM, 8 NFM, 9 WFM, 10 IQ, 11 LBK, 12 RTTY.

**Key offsets:**

| Offset | Field | Conf |
| ---: | --- | --- |
| `0x024` / `0x04C` | VFO A / VFO B records (frequency u64, filter edges, mode, notch, DNR, squelch, AGC, ATT, PRE) | VERIFIED |
| `0x07B` | RF gain | VERIFIED |
| `0x088` | sample-rate / spectrum-span index | HIGH |
| `0x098` | selected VFO | VERIFIED |
| `0x09F` | antenna select (selects the ATU table block) | HIGH |
| `0x0DA`–`0x0E6` | TX filter edges (SSB LPF/HPF, AM LPF, FM LPF) | VERIFIED |
| `0x0EA` / `0x117` / `0x11F` | VOX timeout / threshold / switch | VERIFIED |
| `0x102`–`0x106` | RX EQ bands | VERIFIED |
| `0x154` | TX power (f32 W) | VERIFIED |
| `0x158` | acknowledge of the last `0x08` sequence number | VERIFIED |
| `0x15E` | PTT sources (built-in, CW serial key, tune, SWR/tune, CI-V) | VERIFIED |
| `0x174`–`0x180` | IPv4 address, gateway, netmask, LAN base port | VERIFIED |
| `0x182` | LAN mode (1 = wfview, else HDSDR) | VERIFIED |
| `0x183` / `0x193` | wfview username / password, 16 bytes each, NUL-padded | VERIFIED |

Several of the original partial-map entries were wrong and are
corrected in the CSV: the TX-filter offsets, VOX switch, PTT signals,
port and network mode, and offset `0x158`.

**Filter half-words (VERIFIED).** All edges are in Hz. A zero HPF means
300 Hz, a zero LPF 2700 Hz, and an LPF below its HPF is raised to HPF + 100.
- SSB (modes 0/2): RX LPF `0x0D8`, RX HPF `0x0DC`; TX `0x0DA`/`0x0DE`.
- DIGI (1/3/12): one LPF `0x0D6` for RX and TX; HPF fixed at 300 Hz.
- CW (4): bandwidth `0x0D4` for RX and TX; the filter cutoff is half of
  it, at most 1200 Hz.
- AM/SAM (6/7): `0x0E0` RX, `0x0E2` TX, as full bandwidth (cutoff = half).
- NFM (8): LPF `0x0E4` RX / `0x0E6` TX (full bandwidth), HPF `0x0E8` RX.
- WFM is fixed at 16 kHz. CWR, IQ and LBK get no per-mode edges.

**Fields with no effect in V1.0.1.**
- LINE IN gain `0x0C8` and LINE OUT gain `0x100` (0–30 on Control): no
  code on either unit uses them (VERIFIED).
- `0x08C` (NFM/WFM span index): Main reads it but never copies it from
  `0x01`; it stays at its init value 0 (HIGH). This corrects the earlier
  "ignored by Main" note.
- `0x136` (CW peak filter: a Q = 9 band-pass at the CW pitch): Main copies
  it, but Control always sends 0 (HIGH).
- `0x137`: Control sends its straight-key flag, but Main does not copy it;
  Main's own `0x137` (always 1) enables iambic alternation (HIGH).
- Sidetone loudness: level `0x15A` (0–63) times a Main-only master level
  `0x0CA` (85 of 100), each through a 0 to −50 dB audio taper (VERIFIED).

### `0x03` spectrum and meters (552 B)

**Spectrum.** 512 bytes; the level in dB is the byte value minus 145,
zoomed by setting `0x088`.

**Power-off flag.** Flags bit 2 is set once Main has accepted a
power-off request (PH5 held low for more than 1 s). It persists, and
Main waits 100 ms before shutting down. Control reacts only to this
bit (see `main_unit/docs/flow.md`, Power-on and power-off).

**Tail (40 bytes).** S-meter (dBm), forward power, SWR, Vext, Idd, EALC
and PA temperature as floats, then a reserved word at 0x21C (always
zero) and a flags word at 0x220:
- bit 1 = transmitting;
- bit 2 = Main is powering off;
- bit 3 = SSB/AM squelch closed (with squelch active);
- bit 4 = FM squelch closed (with squelch active);
- bit 5 = LAN PHY link up;
- bit 6 = ADC overload (FPGA status bit 0);
- bit 7 = a network client is active.

Bits 0 and 8–31 are never set. On Control, bits 3/4 show a mute
indicator, bit 6 an overload indicator, bit 7 a remote indicator and
bit 5 a LAN icon (VERIFIED/HIGH).

See `cmd03_fields.csv`.

### `0x06` slave info (104 B)

8 zero bytes, then three 32-byte NUL-terminated strings: MCU version,
FPGA version, and build date/time. See `cmd06_slave_info.csv`.

### `0x08` network state record (46 B)

`[3][seq][0][0]` followed by 42 bytes of TRX fields changed by a
network client: VFO frequencies, filters and modes, the selected VFO,
the span, DNR, VOX, PRE/ATT, RF gain, squelch, MIC gain, TX power and
monitor level. See `cmd08_fields.csv`.

### `0x02` calibration (358 B)

This is an independent EEPROM block (`0x0800`) with its own integrity
fields (VERIFIED):
- layout id 10 at byte 0;
- CRC-8 at `0x164`;
- end marker 0x64 at `0x165`.

It holds the 11-entry TX band-edge table (start/end in Hz plus an
enable) and the three PA bias DAC values (driver, final 1, final 2). See
`cal02_fields.csv`.

### TRX struct runtime tail

Past the 0x1A8-byte settings image, the TRX struct holds Main-only
runtime state: the shadow of the active VFO, the PA drive DAC code,
RIT/XIT as i32, the ADC maximum, TX-state flags, the per-source PTT
flags and the global TX enable. This part is partial; see
`main_unit/analysis/memory/trx_runtime_fields.csv`.

**Why this needed the firmware:** field offsets, units and scaling,
which side writes a field, and the checksum and marker scheme are
invisible on the wire without the producer and consumer code.

> **Decoding key:** the front-panel menu catalog in
> [`hardware.md`](hardware.md) §5 lists the authoritative parameter set
> and value ranges (PRE1/2, AGC modes, EQ-RX/EQ-AMFM 5-band center
> frequencies, FIL1/2/3 + OPT-FILT, TXBW WIDE/MID/NAR, CW iambic/QSK/
> DI-DA, FFT span/zoom, VOX, COMP ratio, NF/NR/NB levels). Match these
> enumerations/ranges against the unmapped `0x01` offsets to finish the
> layout.


## Message types — complete map, VERIFIED

These are all the frame types either firmware builds or dispatches
(VERIFIED by every SLIP-encoder and CRC call site on both units).
Sizes, directions and call sites are VERIFIED; timing has the
confidence noted. Table form: `main_unit/analysis/protocol/msg_types.csv`.

| Type | Direction | Payload | Purpose | Pairing / timing |
| ---: | --- | --- | --- | --- |
| `0x01` | Control→Main | 424 B | front-panel settings image (layout of the Main settings struct) | Sent from the Control TIM13 "SLIP client" callback every period while the TX lock is free (period 20 ms: TIM13 at 50 Hz, VERIFIED). Main counts main-loop passes since the last `0x01`; after ~1000 passes (~2–3 s) it logs the controller as offline and drops PTT/key/tune. Byte `0x158` carries the acknowledge for `0x08`. |
| `0x02` | requester→Main (5-B request or full-length set); Main→requester (358-B reply) | 358 B | calibration block (`0x24013AA4`) | A 5-B request gets the block back. A full-length frame overwrites the RAM copy only; this handler does not write the EEPROM (but the block is saved at shutdown if the boot bias trim set the calibration dirty flag; see `main_unit/docs/memory_map.md`). Control V1.0.1 never sends `0x02` (VERIFIED), so it is probably meant for a factory/calibration tool (HYPOTHESIS). |
| `0x03` | Main→Control | 552 B | 512-B spectrum plus 40-B meter/status tail | Built in the TIM7 interrupt path (`FUN_0804995c`). After sending, Main raises an "FFT wanted" flag, the FFT clears it, and the next frame is built, so the rate follows the FFT. A frame is skipped while the TX lock is busy, and Control drops new data until it has consumed the previous frame. |
| `0x06` | Control→Main (5-B request); Main→Control (104-B reply) | 104 B | slave info (versions) | Control's state machine (`FUN_08034c0c`) sends the request on UI demand and retries every 100 ms until a reply arrives. Main answers any `0x06`. |
| `0x08` | Main→Control | 46 B | TRX state changed by a network client (wfview/CI-V) | Active only while a network client controls the radio. Sent when the 42-B snapshot changes and resent at least every 300 ms until Control echoes its sequence number in `0x01` byte `0x158`, so delivery is reliable (HIGH CONFIDENCE). |

**Reliable state push (`0x08`).** The record is `[3][seq][0][0]`
followed by 42 bytes of TRX fields:
- byte 0 is the sub-type and must be 3;
- `seq` runs 1–255, wraps and is never 0.

Main keeps a "pending" copy and an "acked" copy, and compares each new
snapshot with the pending copy (or with the acked copy if nothing is
pending). When Control echoes the pending `seq`, the pending copy
becomes the acked one. A change in network-control state fills the
acked copy with 0xFF to force a full resend.

**Buffers and locks.**
- **Main:** decoded buffer `0x24018B30`, TX build buffer `0x24017F30`,
  encoded buffer `0x30005360`, TX-busy lock `0x24017F28`. The lock is
  cleared by the TX-complete callback `FUN_08049638`.
- **Control:** ring `0x38000000`, decoded buffer `0x240033EC`, TX build
  buffer `0x240063EC`, encoded buffer `0x38001000`, lock `0x240073F0`.
  The lock is cleared by `FUN_08034BF0`.

**Why this needed the firmware:** reserved header bytes, the ack scheme
inside the payload, the timers behind each type, and the fact that
`0x02` has no sender are software choices. A capture of the wire would
show frames but not their purpose or what is unused.

## Link state machine — VERIFIED unless noted

**Start-up.**
- **Main speaks first.** Main sends `0x03` from boot and never waits
  for Control. Until the first `0x01` arrives, it runs on its stored
  settings and has no offline timer running.
- **Control starts early.** Control starts its 20 ms SLIP client early
  in boot, before its settings exist. The first `0x01` frames carry an
  all-zero image, then the compiled defaults. The values loaded from
  its configuration file appear only once its superloop runs, a few
  seconds after power-up (HIGH CONFIDENCE).
- **Last image wins.** Main applies every `0x01` by diffing it against
  its working copy.

**Steady state.**
- **Control → Main.** Control sends `0x01` every 20 ms while its TX lock
  is free. There is no acknowledge: each frame is a full state image.
- **Main → Control.** Main sends `0x03` once per FFT frame and `0x08` on
  change. A pass that sends `0x08` skips that pass's `0x03`.
- **Requests.** Control repeats the 5-byte `0x06` every 100 ms until
  the reply arrives. Main waits up to 100 ms for its TX lock before
  answering `0x02`/`0x06`; on timeout it frees the lock and drops the
  reply.

**TX locks.** Each side has one lock. The frame builder sets it and
the UART TX-complete callback clears it. Periodic builders skip a frame
while the lock is busy. The Control lock has no timeout.

**Link loss.**
- **Main.** Every `0x01` reloads a 1000-pass countdown (about 2–3 s).
  When it expires, Main logs once and drops the built-in PTT, CW key and
  tune requests. All other settings stay as they are, and
  `0x03`/`0x08` keep flowing.
- **Control** has no timeout. Its display freezes until frames return
  (MEDIUM CONFIDENCE).
- **Recovery** needs no handshake: the next valid `0x01` restarts the
  countdown and is diff-applied.

**Network hand-over.** While a network client controls the radio, Main
ignores the `0x01` VFO block and sets `0x03` flags bit 7. If wfview
streaming is lost, Main keeps network ownership until one of these:
- streaming resumes;
- the client disconnects normally;
- 60 s or three revival attempts pass.

SLIP traffic is never paused.

**Power-off.** See `main_unit/docs/flow.md` (Power-on and power-off).
This is the only time Control saves its settings.

**RX re-arm.** After 100 polls without progress and with overrun set,
Main resets its RX DMA (about 200 ms) and Control restarts its
receive-to-idle DMA (about 2 s).

## Primitives (reference)

| Role | Main Unit | Control Unit |
| --- | --- | --- |
| RX handler (superloop) | `FUN_08049658` | `FUN_08034984` (VERIFIED) |
| SLIP decode | `FUN_0804a258` | `FUN_08052be4` (VERIFIED) |
| SLIP encode | `FUN_0804a200` | `FUN_08052b8c` (VERIFIED) |
| CRC-16/ARC | `FUN_0804ae3c` | `FUN_08052c44` (VERIFIED) |
| TX frame | `FUN_08030358` | `FUN_0802f2f4` (HAL UART DMA transmit) (HIGH CONFIDENCE) |
| RX re-arm | — | `FUN_080300a4` (receive-to-idle DMA restart) (HIGH CONFIDENCE) |
| debug log | `FUN_08021eb0` (printf-style) (HIGH CONFIDENCE) | — |
| memcpy | `FUN_080540ca` | `FUN_0808750a` (HIGH CONFIDENCE) |

Evidence: `*/analysis/protocol/`.

## Unknowns

- Who sends `0x02` in the field (a factory tool?).
- What Main does with the all-zero `0x01` images at Control boot.
- Direction/role handshake and the CH394-Ethernet relationship.
