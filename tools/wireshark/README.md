# Wireshark dissectors for the G7250 LAN services

> **Status: untested in Wireshark.** Both dissectors passed a static
> Lua structure check only; they have not yet been loaded in Wireshark or
> run against real captures. Expect fixes after the first real test.

Two Lua dissectors for the UDP services of the Main Unit (CH394 LAN):

| File | Protocol | Ports |
| --- | --- | --- |
| `g7250_hdsdr.lua` | HDSDR / IQ mode (`g7250_hdsdr`) | UDP 50002, plus a heuristic on any UDP port |
| `g7250_wfview.lua` | wfview mode, Icom-style emulation (`g7250_wfview`) | base port P, P+1 (CI-V), P+2 (audio); P is a preference, default 50001 |

## Independent implementation

These dissectors were written **only from this repository's
documentation**: `main_unit/docs/network.md`,
`main_unit/analysis/peripherals/ch394_network.csv`, `docs/civ.md` and
`docs/protocol.md`. No firmware image, disassembly or vendor code was
used. Anything the documentation does not state is either a preference
or shown as `Unknown bytes`.

The one exception is the 16-byte common header of the wfview packets
(length, type, sequence, sender id, receiver id, little-endian). The
documentation says only that the radio emulates an Icom network radio.
The header layout follows the generally known public description of
that protocol. You can switch it off with the *Decode Icom common
header* preference.

## Install

1. Find your personal Lua plugins folder: in Wireshark, open
   *Help → About Wireshark → Folders → Personal Lua Plugins*. It is
   usually `~/.local/lib/wireshark/plugins` (Linux, macOS) or
   `%APPDATA%\Wireshark\plugins` (Windows).
2. Copy both `.lua` files into that folder.
3. Restart Wireshark, or reload the plugins with *Analyze → Reload Lua
   Plugins* (Ctrl+Shift+L).

You can also load a file for a single run:

```sh
tshark -X lua_script:g7250_hdsdr.lua -X lua_script:g7250_wfview.lua -r capture.pcap
```

Requires Wireshark 3.x or later (it uses `ProtoExpert` and
`register_heuristic`).

## Usage

- **Display filters:** `g7250_hdsdr`, `g7250_hdsdr.cmd == 0x0103`,
  `g7250_wfview.socket == 1`, `g7250_wfview.civ.cmd == 0x25`,
  `g7250_wfview.civ.freq`.
- **Expert info:** *Analyze → Expert Information*. It flags malformed
  packets (bad magic, short packets, IQ packets that are not 774 bytes,
  header-length mismatch, CI-V frames without `FD`) and protocol notes
  (LO outside 0.5–108 MHz, CI-V to-address the radio ignores, mode 06
  applied as LSB, audio chunks over 1364 bytes).
- **Preferences:** *Edit → Preferences → Protocols*.

### HDSDR preferences (`g7250_hdsdr`)

| Preference | Default | Why |
| --- | --- | --- |
| Payload fields little-endian | off | The byte order of the port, LO and device id is undocumented; only the command word is documented as big-endian. |
| IQ samples big-endian | off | The sample byte order is undocumented. |
| List individual IQ samples | off | Adds 192 tree items per packet. |

Layout used: magic (4), command (2, big-endian), then:
- discover: PC IPv4 (4) and port (2);
- set LO: Hz as a 64-bit value (8);
- report: radio IPv4 (4), port (2) and device id (4);
- IQ: 192 × (I int16, Q int16).

The documentation gives the field order and sizes but not the exact
payload lengths; bytes past these fields are shown as unknown.

### wfview preferences (`g7250_wfview`)

| Preference | Default | Why |
| --- | --- | --- |
| Base UDP port | 50001 | Set on the radio (settings offset 0x180). |
| Decode Icom common header | on | The header is not in the repository documentation. |
| Audio is 8-bit | off | The client negotiates 16-bit or 8-bit LPCM; the negotiation body is not decoded. |
| Audio header length | 0x18 | Bytes before the samples; undocumented. |
| CI-V search start | 0x10 | The CI-V socket payload is scanned for `FE FE … FD` from this offset. |

What is decoded:
- **Control socket.** Packet types are named: are-you-there, I-am-here,
  are-you-ready/ready, ping, retransmit, disconnect and idle. Data
  packets are named login, token, capabilities, conninfo or status by
  their usual length only, and marked as a guess. Their bodies are
  unknown bytes, and credentials are not decoded. A datagram with no
  valid header that is printable text is shown as a plain-text probe.
- **CI-V socket.** Every `FE FE <to> <from> <cmd> … FD` frame is
  decoded. Top-level command names come from `docs/civ.md`.
  Frequencies in 00, 03 and 25 are decoded as Icom BCD. The 0x29 VFO
  prefix is unwrapped. Sub-command numbers are shown raw, because the
  documentation does not list them.
- **Audio socket.** The LPCM chunk length and sample count are shown.

### Port overlap

The HDSDR port 50002 is also P+1 when wfview uses the default base port.
The two modes never run at the same time, so each dissector hands
packets to the other: wfview passes on packets that start with
`AA 55 55 AA`, and HDSDR passes on packets without that magic.

## Limitations

- The radio's multi-byte payload byte orders are not documented (see
  the preferences).
- The handshake bodies and the CI-V and audio data headers are shown as
  unknown bytes. A multi-entry retransmit request is read as a list of
  16-bit sequence numbers, which is a guess.
- Each datagram is decoded on its own; handshake state is not
  tracked across packets.
