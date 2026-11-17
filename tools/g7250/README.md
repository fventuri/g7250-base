# G7250 reference tooling

Small Python 3 tools (standard library only) for the two documented
G7250 protocols:

- `slip.py`: the inter-MCU UART link (Main Unit to Control Unit): SLIP
  framing, CRC-16/ARC, the `[type][0][0] payload crc16` frame and
  CSV-driven parsers for message types `0x01`, `0x02`, `0x03`, `0x06`
  and `0x08`.
- `hdsdr_client.py`: a receive-only client for the HDSDR / IQ LAN mode
  (discover, heartbeat, set LO, I/Q reception to WAV or raw).

## Independent implementation

This is a clean-room implementation. It was written only from this
repository's documentation:
- `docs/protocol.md` and `main_unit/docs/network.md`;
- `main_unit/analysis/protocol/*.csv`;
- `main_unit/analysis/peripherals/ch394_network.csv`.

No firmware image, disassembly or decompiled code was consulted, and no
vendor code or strings are included. Where the docs leave a detail
open, the code states its assumption (see "Assumptions" below).

## Inter-MCU codec (`slip.py`)

```python
from g7250 import slip

wire = slip.build_frame(slip.MSG_SLAVE_INFO)   # 5-byte request, SLIP-encoded
for pkt in slip.slip_decode_stream(wire):
    frame = slip.parse_packet(pkt)              # checks length and CRC
    fields = slip.parse_message(frame)          # {field name: value}
```

Field offsets, widths and types are read from the CSVs at run time, so
an update to the CSVs changes the parser without a code change. The
CSV directory is found in this order:
1. the `--csv-dir` argument (or the `csv_dir` parameter);
2. the `G7250_PROTOCOL_DIR` environment variable;
3. `main_unit/analysis/protocol` in a parent directory of the module
   (the repository layout).

Decode a raw UART capture file (for example from a logic analyser
export):

```sh
cd tools
python3 -m g7250.slip capture.bin --fields
```

## HDSDR / IQ client (`hdsdr_client.py`)

Without `--host` the client is a **dry run**: it prints the packets it
would send and opens no socket.

```sh
cd tools
python3 -m g7250.hdsdr_client --lo 7074000                 # dry run
python3 -m g7250.hdsdr_client --host 192.168.1.50 --lo 7074000 \
    --duration 30 --output iq.wav                           # live
```

In live mode it sends a discover to UDP port 50002 and then a heartbeat
every 2 s, which is inside the 10 s session timeout. It receives `0x0202`
I/Q packets on `--local-port` (default 50001). Options:
- `--format wav` (default) writes a stereo 16-bit 48 kHz WAV with I on
  the left and Q on the right;
- `--format raw` writes interleaved int16 little-endian.

**Receive only.** The client can build only the three PC-to-radio
commands (`0x0101`, `0x0102`, `0x0103`). Any other command is refused.
The HDSDR protocol has no transmit command, and this tool never keys TX.

## Assumptions

These points are not stated in the docs. Check them against a capture:
- **Inter-MCU payloads.** Multi-byte payload fields are little-endian,
  like the documented CRC and both MCUs.
- **IPv4 at `0x174`–`0x17C`.** The address is a u32 whose most
  significant byte is the first octet (`ipv4_from_u32`).
- **`0x08` field types.** The CSV has no type column, so types come
  from the width. A field is `f32` when its name says so.
- **HDSDR fields.** Fields after the 16-bit command (IPv4, port, LO,
  device id) are big-endian like the command. The report layout is
  IPv4 (4 B), port (2 B), device id (4 B).
- **I/Q byte order.** Samples are little-endian. `--iq-endian big`
  switches it.

## Tests

The tests use synthetic vectors only. They need no radio and no network.

```sh
cd tools
python3 -m unittest discover -s g7250/tests -t .
```

The CSV-driven tests find the repository CSVs automatically. Outside
the repo, set `G7250_PROTOCOL_DIR`; if no CSVs are found, those tests
are skipped.
