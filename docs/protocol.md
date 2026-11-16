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
  8192 B control).
- RX handlers:
  - Main Unit: `FUN_08049658`, polled from the superloop.
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
  logged as `Invalid SLIP Packet, raw_len=…, dec_len=…`.
- Mismatch logs `Wrong CRC, mine = %04X, thires = %04X` ("thires" is an
  OEM typo for "theirs" = received CRC).
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
  `FUN_08041EF4` (diffs each field vs. a working copy and logs changes).
- **`0x02` = calibration data** (`[DBG] Get calibrate data`). 358-B block
  at `0x24013AA4`, immediately preceding the TRX-state struct
  (`0x24013C0C`) — one contiguous radio-state region. Referenced by 14
  functions (PA/filter/meter use).
- **`0x06` = "slave info"** (`[DBG] Get slave info`). 104-B block at
  `0x24018F30`.

The Main Unit emulates an **Icom-style network radio for wfview** — the
settings block carries `wfview Username`/`Password`, IPv4 config, and a
"Remote controller off line" state.

### `0x01` settings block — partial field map

Offsets are relative to the payload start (after the 3-byte header),
i.e. into the struct at `0x24018F9C`. Evidence:
`main_unit/analysis/protocol/cmd01_fields.csv` and
`cmd01_consumer_08041ef4.txt`.

| Offset | Type | Field | Conf |
| ---: | --- | --- | --- |
| `0x008` | u32 | flags 1 (bitfield) | HIGH |
| `0x074` | i16 | RIT frequency | HIGH |
| `0x076` | i16 | XIT frequency | HIGH |
| `0x088` | i32 | sample rate | HIGH |
| `0x09F` | u8 | antenna select (bit 0 = ANT index; used by the ATU table) | HIGH |
| `0x0C4` | i16 | MIC gain | HIGH |
| `0x0DA` | i16 | AM LPF TX filter | HIGH |
| `0x0DE` | i16 | SSB LPF TX filter | HIGH |
| `0x0E2` | i16 | FM LPF TX filter | HIGH |
| `0x0E6` | i16 | PTT signals | HIGH |
| `0x0E8` | i16 | SSB HPF TX filter | HIGH |
| `0x0EA` | i16 | VOX switch | HIGH |
| `0x138` | u16 | remote-controller online status | MED |
| `0x154` | f32 | TX power (→ PA DAC value) | HIGH |
| `0x158` | u8 | status flag (checked by RX handler) | MED |
| `0x174` | u32 | IPv4 address | HIGH |
| `0x178` | u32 | IPv4 gateway | HIGH |
| `0x17C` | u32 | IPv4 netmask | HIGH |
| `0x180` | i16 | network mode | HIGH |

The block also carries (offsets not yet pinned, from consumer strings):
selected VFO / frequency / mode, RF gain, XIT/RIT switch, VOX
threshold/timeout, EQ parameters, audio filters, ATU switch, CW zoom,
DNR1/DNR2 threshold, global SQL threshold, monitor level, wfview
username/password, flags 2. Full 424-byte layout is TODO.

The same 424-byte struct is the Main Unit's EEPROM / backup-SRAM
settings image, with validity markers 0x64 at offsets 0x000, 0x1A3 and
0x1A4 (see `main_unit/docs/memory_map.md`).

> **Decoding key:** the front-panel menu catalog in
> [`hardware.md`](hardware.md) §5 lists the authoritative parameter set
> and value ranges (PRE1/2, AGC modes, EQ-RX/EQ-AMFM 5-band center
> frequencies, FIL1/2/3 + OPT-FILT, TXBW WIDE/MID/NAR, CW iambic/QSK/
> DI-DA, FFT span/zoom, VOX, COMP ratio, NF/NR/NB levels). Match these
> enumerations/ranges against the unmapped `0x01` offsets to finish the
> layout.

`0x02` (calibration) and `0x06` (slave info) field layouts are not yet
decoded (mostly numeric tables, few strings).

## Message types — complete map, VERIFIED

These are all the frame types either firmware builds or dispatches
(VERIFIED by every SLIP-encoder and CRC call site on both units).
Sizes, directions and call sites are VERIFIED; timing has the
confidence noted. Table form: `main_unit/analysis/protocol/msg_types.csv`.

| Type | Direction | Payload | Purpose | Pairing / timing |
| ---: | --- | --- | --- | --- |
| `0x01` | Control→Main | 424 B | front-panel settings image (layout of the Main settings struct) | Sent from the Control TIM13 "SLIP client" callback every period while the TX lock is free (period ~20 ms, MEDIUM). Main counts main-loop passes since the last `0x01`; after ~1000 passes (~2–3 s) it logs the controller as offline and drops PTT/key/tune. Byte `0x158` carries the acknowledge for `0x08`. |
| `0x02` | requester→Main (5-B request or full-length set); Main→requester (358-B reply) | 358 B | calibration block (`0x24013AA4`) | A 5-B request gets the block back. A full-length frame overwrites the RAM copy only; this handler does not write the EEPROM. Control V1.0.1 never sends `0x02` (VERIFIED), so it is probably meant for a factory/calibration tool (HYPOTHESIS). |
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

## Primitives (reference)

| Role | Main Unit | Control Unit |
| --- | --- | --- |
| RX handler (superloop) | `FUN_08049658` | `FUN_08034984` |
| SLIP decode | `FUN_0804a258` | `FUN_08052be4` |
| SLIP encode | `FUN_0804a200` | `FUN_08052b8c` |
| CRC-16/ARC | `FUN_0804ae3c` | `FUN_08052c44` |
| TX frame | `FUN_08030358` | `FUN_0802f2f4` (HAL UART DMA transmit) |
| RX re-arm | — | `FUN_080300a4` (receive-to-idle DMA restart) |
| debug log | `FUN_08021eb0` (printf-style) | — |
| memcpy | `FUN_080540ca` | `FUN_0808750a` |

Evidence: `*/analysis/protocol/`.

## Unknowns

- Who sends `0x02` in the field (a factory tool?).
- Direction/role handshake and the CH394-Ethernet relationship.
