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
- RX handlers (polled from each superloop):
  - Main Unit: `FUN_08049658`
  - Control Unit: `FUN_08034984`
- A ~1 s inactivity watchdog re-arms the DMA/UART if the read pointer
  stops moving (handles `USART Overrun`).

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
  it. Observed response frames are built as
  `[type][0][?]<payload><crc16>` (payload begins at offset 3), implying a
  **3-byte header**; the two bytes after `type` are not yet identified.

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

## Message types (observed)

Payload sizes are VERIFIED (memcpy lengths); directions are from which
unit's RX handler decodes them; meanings are HIGH CONFIDENCE / inferred.

| Type | Decoded by | Payload | Notes |
| ---: | --- | ---: | --- |
| `0x01` | Main | 424 B (`0x1A8`) @ off 3 | large state/settings block pushed to Main (copied to a 424-B struct) |
| `0x02` | Main | request (len 5) → reply 363 B; or set (len `0x16B`) | 5-B request ⇒ Main replies with a 358-B (`0x166`) block; full-length frame writes that block |
| `0x03` | Control | 512 B (`0x200`) | block pushed to Control (plus an array re-pack) |
| `0x06` | Main & Control | 104 B (`0x68`) | bidirectional 104-B block (Main can reply on request, len 5) |
| `0x08` | Control | block (array) | pushed to Control |

Request/response uses a lock flag with a ~100 ms timeout; replies are
assembled, CRC-appended, SLIP-encoded, then transmitted:
- Main TX path: `FUN_08030358` (and `FUN_08021eb0` notifies the app).
- Control TX path: `FUN_080300a4`.

## Primitives (reference)

| Role | Main Unit | Control Unit |
| --- | --- | --- |
| RX handler (superloop) | `FUN_08049658` | `FUN_08034984` |
| SLIP decode | `FUN_0804a258` | `FUN_08052be4` |
| SLIP encode | `FUN_0804a200` | (equivalent) |
| CRC-16/ARC | `FUN_0804ae3c` | `FUN_08052c44` |
| TX frame | `FUN_08030358` | `FUN_080300a4` |
| memcpy | `FUN_080540ca` | `FUN_0808750a` |

Evidence: `*/analysis/protocol/`.

## Unknowns

- The 2 header bytes after `type` (seq? address? length? sub-id?).
- Full command-ID map and payload field layouts (424/512/358/104-B
  blocks — these are the radio's shared state; decode next).
- Direction/role handshake and the CH394-Ethernet relationship.
