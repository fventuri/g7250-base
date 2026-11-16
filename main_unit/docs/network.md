# Main Unit — LAN services (CH394)

Status: VERIFIED unless marked. The driver and control pins are in
`peripherals.md` (SPI6 section). Values: `analysis/peripherals/ch394_network.csv`.

## Configuration

- **Static IPv4 only; there is no DHCP code.** IP, gateway, netmask and
  the base port come from the SLIP `0x01` settings block (offsets
  0x174/0x178/0x17C/0x180), which is also persisted in the EEPROM.
- **Service selection.** Byte 0x182 selects the service: 1 = wfview,
  anything else = HDSDR.
- **Live changes.** Changes are applied immediately. A mode change
  closes all sockets and restarts the network layer.
- **Fixed values.** The MAC is read from the CH394, not from the
  EEPROM. The HDSDR port 50002 and the default destination port 50001
  are hard-coded.
- **Not in the MCU.** No ARP, ICMP or other protocol code was found in
  the MCU; the CH394 handles those (HIGH CONFIDENCE).

## Sockets and buffers

The chip has 8 hardware sockets, and only **UDP** is used: no TCP, no
raw modes, no connect/listen. Each mode splits the 16 KB TX and 16 KB
RX pools differently:
- **HDSDR mode:** socket 0 gets all 16 KB.
- **wfview mode:** sockets 1/2/3 get 2/6/8 KB.
- Sockets 4–7 are always unused.

**Sending** (`FUN_08047440`, `FUN_080455dc`):
1. DMA the datagram (1–2048 B) into the socket TX buffer.
2. Set the TX write pointer and issue SEND.
3. Poll the command register. A stuck SEND is logged and retried, at
   most once per 500 ms.

**Receiving** (`FUN_08045de8` for HDSDR, `FUN_080469f8` for the wfview
batch):
1. Read the received size twice, so the value is stable.
2. DMA the 8-byte per-datagram header (peer IP, port, length) and then
   the payload.
3. Write back the read pointer, verify it, and issue RECV.

The batch reader flushes its queue on a header/length desync.

## Link monitoring and self-heal (`FUN_0804905c`)

**Polling.** The PHY configuration register is polled once a second,
and every change is logged.

**Link cycle.** After more than 10 s without link, at most every 30 s,
the firmware cycles the PHY: power-down, 100 ms, all-capable
auto-negotiation, then up to 10 s waiting for link, kicking the
watchdog every 200 ms.

**Escalation.** After two failed cycles it resets the CH394 through its reset
pin once, with a full network re-init, then stops trying.

**Late cable.** A link that appears after a cable-less boot re-inits
the services.

## HDSDR / IQ mode (`FUN_0804aed8`, `FUN_0804af68`, `FUN_0804b184`)

One UDP socket on local port **50002**. Every packet starts with the
4-byte magic `AA 55 55 AA` and a 16-bit big-endian command.

| Command | Direction | Content |
| --- | --- | --- |
| `0x0101` | PC→radio | discover: PC IPv4 and port (if the IPv4 is 0, the source address is used); sets the destination |
| `0x0102` | PC→radio | heartbeat |
| `0x0103` | PC→radio | set LO: 64-bit Hz, accepted 0.5–108 MHz |
| `0x0201` | radio→PC | report: radio IPv4, port 50002, 4-byte device id |
| `0x0202` | radio→PC | IQ: 192 complex int16 samples (I, Q interleaved), 774 bytes per packet |

The session drops after 10 s without a heartbeat or discover. The IQ is
the 48 kHz decimated receiver I/Q, taken in the RX DSP routine
(`FUN_08033610`) before demodulation, from the ping-pong buffers
`0x38001000` / `0x38001300`.

## wfview mode — Icom-network emulation (`FUN_0804db5c`, `FUN_0804bc90`, `FUN_0804de38`)

**Sockets.** Three UDP sockets: control on the base port (settings
0x180), CI-V on base+1, audio on base+2. The radio presents itself as an
IC-7300, with CI-V address 0xA0 and an Icom-style virtual audio device.

**Handshake:**
1. An are-you-there packet, or a plain-text probe, gets I-am-here.
2. Are-you-ready gets a ready reply.
3. Login: the user and password are compared with settings 0x183 and
   0x193 after the standard Icom character obfuscation.
4. Token.
5. The radio sends its capabilities and conninfo.
6. The client's conninfo carries its ports, codecs and sample rates;
   the radio answers with a status packet.
7. Streaming starts.

**Keep-alive.** Pings go out every 100 ms on control and CI-V and every
500 ms on audio. Retransmit requests are served from a sent-packet ring
(`0x30002740`).

**Audio.** LPCM 16-bit or 8-bit mono, at 48 or 16 kHz. Other client
codecs (µ-law, Opus, stereo) are rejected with a warning. RX audio goes
out every 20 ms in chunks of at most 1364 bytes. TX audio feeds the TX
DSP.

**Timeouts.** Login, capabilities, conninfo and stream start each have
5 s. CI-V and audio streams are dropped after 15 s of silence.

**Recovery ladder:**
1. Reopen a socket after repeated foreign-source or length errors.
2. Reopen after lost pongs.
3. Three reopens without a cure, a "whole chip silent" condition, or a
   handshake stuck before login lead to a PHY link cycle and then a
   hardware reset of the CH394.
4. A fuse suspends automatic recovery for 5 minutes after 3 resets in
   60 s.

When streaming is lost, Main keeps network ownership for up to 60 s or
three revival attempts. During that time the front panel's VFO settings
stay ignored; SLIP traffic itself is not interrupted.

**CI-V layer (PARTIAL, structure HIGH CONFIDENCE).** A parser at
`0x080504E8` finds FE FE … FD frames and accepts only address 0xA0 or
broadcast 0x00. Commands 0x00–0x06 have their own path; 0x07–0x29 go
through a 35-entry jump table (`0x080505A0`), with sub-tables at
`0x08050B40` and `0x08050CC0`. Handlers cover VFO operations, split,
attenuator, antenna, levels and meters, functions (NB, NR, notch, VOX,
break-in), power, ATU/PTT, RIT, frequency and mode, and the scope. The
full command map is open.

**Why this needed the firmware:** the CH394 datasheet gives only the
register set. The socket plan, the UDP application protocols, ports,
credential handling, keep-alive and timeout values, and the self-heal
policy are documented nowhere else.
