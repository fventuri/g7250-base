#!/usr/bin/env python3
"""Inter-MCU link codec for the G7250 (Main Unit <-> Control Unit).

Independent implementation written from docs/protocol.md and the field
tables in main_unit/analysis/protocol/*.csv. Offsets are not hard-coded:
the parse helpers load the CSVs at run time.

Wire format (docs/protocol.md):
    SLIP(  [type][0x00][0x00] <payload> <crc16 little-endian>  ) 0xC0
CRC-16/ARC covers everything before the two CRC bytes.

Byte order of multi-byte payload fields is not stated in the docs; both
MCUs are little-endian Cortex-M7 parts, so little-endian is assumed here
(the CRC is documented as little-endian).
"""
from __future__ import annotations

import argparse
import csv
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

# --- SLIP (RFC 1055) --------------------------------------------------------

END = 0xC0
ESC = 0xDB
ESC_END = 0xDC
ESC_ESC = 0xDD


def slip_encode(data: bytes) -> bytes:
    """Encode one frame: escape END/ESC, add one trailing END, no leading END."""
    out = bytearray()
    for b in data:
        if b == END:
            out += bytes((ESC, ESC_END))
        elif b == ESC:
            out += bytes((ESC, ESC_ESC))
        else:
            out.append(b)
    out.append(END)
    return bytes(out)


class SlipError(ValueError):
    """Malformed SLIP escape sequence."""


def slip_unescape(body: bytes) -> bytes:
    """Undo SLIP escaping for one frame body (no END bytes inside)."""
    out = bytearray()
    it = iter(body)
    for b in it:
        if b == ESC:
            nxt = next(it, None)
            if nxt == ESC_END:
                out.append(END)
            elif nxt == ESC_ESC:
                out.append(ESC)
            else:
                raise SlipError(f"bad escape sequence DB {nxt!r}")
        else:
            out.append(b)
    return bytes(out)


class SlipDecoder:
    """Streaming decoder. Feed bytes, get complete frames; empty frames skipped."""

    def __init__(self, max_len: int = 8192) -> None:
        self._buf = bytearray()
        self.max_len = max_len

    def feed(self, data: bytes) -> list[bytes]:
        frames: list[bytes] = []
        for b in data:
            if b == END:
                if self._buf:
                    frames.append(slip_unescape(bytes(self._buf)))
                    self._buf.clear()
            else:
                self._buf.append(b)
                if len(self._buf) > 2 * self.max_len:
                    self._buf.clear()  # overflow: drop the partial frame
        return frames


def slip_decode_stream(data: bytes) -> list[bytes]:
    """Decode every complete frame in a byte string."""
    return SlipDecoder().feed(data)


# --- CRC-16/ARC -------------------------------------------------------------

def _make_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        table.append(crc)
    return table


_CRC_TABLE = _make_table()


def crc16_arc(data: bytes, crc: int = 0x0000) -> int:
    """CRC-16/ARC: poly 0x8005 reflected, init 0, no xorout."""
    for b in data:
        crc = _CRC_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc


# --- Frame header and message types ----------------------------------------

MSG_SETTINGS = 0x01      # Control -> Main, 424-B settings image
MSG_CALIBRATION = 0x02   # 5-B request / 358-B block
MSG_SPECTRUM = 0x03      # Main -> Control, 512-B spectrum + 40-B tail
MSG_SLAVE_INFO = 0x06    # 5-B request / 104-B version strings
MSG_NET_STATE = 0x08     # Main -> Control, 46-B network state record

MSG_NAMES = {
    MSG_SETTINGS: "settings",
    MSG_CALIBRATION: "calibration",
    MSG_SPECTRUM: "spectrum+meters",
    MSG_SLAVE_INFO: "slave info",
    MSG_NET_STATE: "network state",
}

PAYLOAD_LEN = {
    MSG_SETTINGS: 0x1A8,
    MSG_CALIBRATION: 0x166,
    MSG_SPECTRUM: 0x228,
    MSG_SLAVE_INFO: 0x68,
    MSG_NET_STATE: 0x2E,
}

HEADER_LEN = 3            # type + two reserved zero bytes
CRC_LEN = 2
MIN_FRAME_LEN = HEADER_LEN + CRC_LEN  # 5: also the request frame size


class FrameError(ValueError):
    """Frame too short or CRC mismatch."""


@dataclass(frozen=True)
class Frame:
    msg_type: int
    reserved: bytes
    payload: bytes

    @property
    def name(self) -> str:
        return MSG_NAMES.get(self.msg_type, f"unknown 0x{self.msg_type:02X}")


def build_packet(msg_type: int, payload: bytes = b"") -> bytes:
    """Decoded packet: [type][0][0] payload crc16-LE."""
    body = bytes((msg_type & 0xFF, 0, 0)) + payload
    return body + struct.pack("<H", crc16_arc(body))


def build_frame(msg_type: int, payload: bytes = b"") -> bytes:
    """Wire bytes for one message (packet + SLIP)."""
    return slip_encode(build_packet(msg_type, payload))


def parse_packet(packet: bytes) -> Frame:
    """Check length and CRC of a decoded packet and split it."""
    if len(packet) < MIN_FRAME_LEN:
        raise FrameError(f"frame too short ({len(packet)} B)")
    body, rx = packet[:-CRC_LEN], struct.unpack("<H", packet[-CRC_LEN:])[0]
    calc = crc16_arc(body)
    if calc != rx:
        raise FrameError(f"CRC mismatch: computed 0x{calc:04X}, received 0x{rx:04X}")
    return Frame(body[0], body[1:HEADER_LEN], body[HEADER_LEN:])


# --- CSV-driven field parsing ----------------------------------------------

CSV_DIR_ENV = "G7250_PROTOCOL_DIR"
_REL_CSV_DIR = Path("main_unit") / "analysis" / "protocol"

FIELD_CSV = {
    MSG_SETTINGS: "cmd01_fields.csv",
    MSG_CALIBRATION: "cal02_fields.csv",
    MSG_SPECTRUM: "cmd03_fields.csv",
    MSG_SLAVE_INFO: "cmd06_slave_info.csv",
    MSG_NET_STATE: "cmd08_fields.csv",
}
VFO_RECORD_CSV = "cmd01_vfo_record.csv"


def find_csv_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Locate the protocol CSVs: argument, $G7250_PROTOCOL_DIR, or repo root above."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(CSV_DIR_ENV)
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        cand = parent / _REL_CSV_DIR
        if cand.is_dir():
            return cand
    raise FileNotFoundError(
        f"protocol CSVs not found; set {CSV_DIR_ENV} or pass --csv-dir")


@dataclass(frozen=True)
class Field:
    offset: int
    width: int
    ftype: str
    name: str
    bit: int | None = None   # set for single-bit rows such as 0x220.b1


def _infer_type(width: int, name: str) -> str:
    """cmd08 has no type column: infer from width (f32 if the name says so)."""
    if "f32" in name:
        return "f32"
    return {1: "u8", 2: "u16", 4: "u32", 8: "u64"}.get(width, "bytes")


def load_fields(csv_name: str, csv_dir: Path | None = None) -> list[Field]:
    """Read a field CSV (columns offset|rel, width, [type], field)."""
    path = find_csv_dir(csv_dir) / csv_name
    fields: list[Field] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            off_text = row.get("offset") or row.get("rel") or ""
            name = row.get("field", "").strip()
            bit: int | None = None
            if ".b" in off_text:
                base, bits = off_text.split(".b", 1)
                if "-" in bits:
                    continue  # "never set" bit ranges carry no value
                off_text, bit = base, int(bits)
            width = int(row["width"])
            ftype = (row.get("type") or "").strip() or _infer_type(width, name)
            if bit is not None:
                ftype = "bit"
            fields.append(Field(int(off_text, 16), width, ftype, name, bit))
    return fields


_SCALAR = {"u8": "<B", "i8": "<b", "u16": "<H", "i16": "<h",
           "u32": "<I", "i32": "<i", "u64": "<Q", "f32": "<f"}


def decode_value(ftype: str, raw: bytes) -> Any:
    """Turn raw bytes into a Python value according to a CSV type string."""
    if ftype in _SCALAR and len(raw) == struct.calcsize(_SCALAR[ftype]):
        return struct.unpack(_SCALAR[ftype], raw)[0]
    if ftype.startswith("char["):
        return raw.split(b"\x00", 1)[0].decode("ascii", "replace")
    if "[" in ftype or "x" in ftype:   # i8[5], u8[512], f32[8], u16x2
        elem = ftype.split("[", 1)[0].split("x", 1)[0]
        if elem in _SCALAR:
            size = struct.calcsize(_SCALAR[elem])
            if size and len(raw) % size == 0:
                return list(struct.unpack(f"<{len(raw) // size}{_SCALAR[elem][1]}", raw))
    return raw.hex()


def parse_fields(payload: bytes, fields: Iterable[Field],
                 csv_dir: Path | None = None) -> dict[str, Any]:
    """Map field name -> value; nested VFO records use cmd01_vfo_record.csv."""
    out: dict[str, Any] = {}
    vfo_fields: list[Field] | None = None
    for f in fields:
        key = f.name if f.name not in out else f"{f.name} @0x{f.offset:03X}"
        raw = payload[f.offset:f.offset + (4 if f.bit is not None else f.width)]
        if f.bit is not None:
            out[key] = bool((struct.unpack("<I", raw)[0] >> f.bit) & 1)
        elif f.ftype == "struct" and "VFO" in f.name:
            if vfo_fields is None:
                vfo_fields = load_fields(VFO_RECORD_CSV, csv_dir)
            out[key] = parse_fields(raw, vfo_fields, csv_dir)
        else:
            out[key] = decode_value(f.ftype, raw)
    return out


def parse_message(frame: Frame, csv_dir: Path | None = None) -> dict[str, Any]:
    """Decode a frame payload with the matching CSV. Requests return {}."""
    csv_name = FIELD_CSV.get(frame.msg_type)
    if csv_name is None or not frame.payload:
        return {}
    expected = PAYLOAD_LEN[frame.msg_type]
    if len(frame.payload) != expected:
        raise FrameError(f"type 0x{frame.msg_type:02X}: payload {len(frame.payload)} B, "
                         f"expected {expected} B")
    return parse_fields(frame.payload, load_fields(csv_name, csv_dir), csv_dir)


def ipv4_from_u32(value: int) -> str:
    """Format a u32 whose most significant byte is the first octet."""
    return ".".join(str((value >> s) & 0xFF) for s in (24, 16, 8, 0))


# --- CLI: decode a captured byte stream ------------------------------------

def iter_messages(data: bytes) -> Iterator[Frame | FrameError]:
    for pkt in slip_decode_stream(data):
        try:
            yield parse_packet(pkt)
        except FrameError as exc:
            yield exc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Decode a raw inter-MCU UART capture file.")
    ap.add_argument("capture", help="binary file with the raw UART byte stream")
    ap.add_argument("--csv-dir", help=f"protocol CSV directory (default: ${CSV_DIR_ENV} "
                                      "or the repo tree)")
    ap.add_argument("--fields", action="store_true", help="print decoded payload fields")
    args = ap.parse_args(argv)
    data = Path(args.capture).read_bytes()
    csv_dir = Path(args.csv_dir) if args.csv_dir else None
    for i, item in enumerate(iter_messages(data)):
        if isinstance(item, FrameError):
            print(f"#{i}: invalid: {item}")
            continue
        print(f"#{i}: type 0x{item.msg_type:02X} ({item.name}), {len(item.payload)} B payload")
        if args.fields:
            for name, value in parse_message(item, csv_dir).items():
                if isinstance(value, list) and len(value) > 16:
                    value = f"[{len(value)} values]"
                print(f"    {name}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
