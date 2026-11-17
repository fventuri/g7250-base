#!/usr/bin/env python3
"""Receive-only client for the G7250 HDSDR / IQ LAN mode.

Independent implementation written from main_unit/docs/network.md and
main_unit/analysis/peripherals/ch394_network.csv.

Documented protocol: UDP, radio port 50002, every packet starts with the
magic AA 55 55 AA and a 16-bit big-endian command.
    0x0101 PC->radio  discover: PC IPv4 + port (IPv4 0 = use source address)
    0x0102 PC->radio  heartbeat (session drops after 10 s without one)
    0x0103 PC->radio  set LO: 64-bit Hz, accepted 0.5-108 MHz
    0x0201 radio->PC  report: radio IPv4, port 50002, 4-byte device id
    0x0202 radio->PC  IQ: 192 complex int16 (I, Q interleaved), 774 B

ASSUMPTIONS (not stated in the docs; check against a capture):
  * multi-byte fields after the command are big-endian like the command;
  * the int16 I/Q samples are little-endian (MCU native); see --iq-endian.

Safety: the client can only build the three PC->radio commands above.
The HDSDR protocol has no transmit command, and this tool never keys TX.
Without --host it only prints the packets it would send (dry run).
"""
from __future__ import annotations

import argparse
import ipaddress
import socket
import struct
import sys
import time
import wave
from dataclasses import dataclass
from typing import BinaryIO

MAGIC = bytes.fromhex("AA5555AA")
RADIO_PORT = 50002
DEFAULT_LOCAL_PORT = 50001   # the radio's hard-coded default destination port

CMD_DISCOVER = 0x0101
CMD_HEARTBEAT = 0x0102
CMD_SET_LO = 0x0103
CMD_REPORT = 0x0201
CMD_IQ = 0x0202

PC_COMMANDS = frozenset({CMD_DISCOVER, CMD_HEARTBEAT, CMD_SET_LO})

LO_MIN_HZ = 500_000
LO_MAX_HZ = 108_000_000
IQ_PAIRS = 192
IQ_PACKET_LEN = 774          # 4 magic + 2 cmd + 192 * 2 * 2
SAMPLE_RATE = 48_000
SESSION_TIMEOUT_S = 10.0
HEARTBEAT_PERIOD_S = 2.0     # well inside the 10 s session timeout

HEADER = struct.Struct(">4sH")


class PacketError(ValueError):
    """Bad magic, unknown command or wrong length."""


# --- Packet builders (PC -> radio) -----------------------------------------

def _packet(cmd: int, body: bytes = b"") -> bytes:
    if cmd not in PC_COMMANDS:
        raise ValueError(f"refusing to build command 0x{cmd:04X}")
    return HEADER.pack(MAGIC, cmd) + body


def build_discover(pc_ip: str = "0.0.0.0", pc_port: int = DEFAULT_LOCAL_PORT) -> bytes:
    """Discover; pc_ip 0.0.0.0 tells the radio to use the source address."""
    return _packet(CMD_DISCOVER, ipaddress.IPv4Address(pc_ip).packed + struct.pack(">H", pc_port))


def build_heartbeat() -> bytes:
    return _packet(CMD_HEARTBEAT)


def build_set_lo(freq_hz: int) -> bytes:
    if not LO_MIN_HZ <= freq_hz <= LO_MAX_HZ:
        raise ValueError(f"LO {freq_hz} Hz outside {LO_MIN_HZ}-{LO_MAX_HZ} Hz")
    return _packet(CMD_SET_LO, struct.pack(">Q", freq_hz))


# --- Packet parsers (radio -> PC) ------------------------------------------

@dataclass(frozen=True)
class Report:
    ip: str
    port: int
    device_id: bytes


@dataclass(frozen=True)
class IQBlock:
    samples: tuple[int, ...]   # interleaved I, Q, I, Q ...

    @property
    def pairs(self) -> list[tuple[int, int]]:
        s = self.samples
        return list(zip(s[0::2], s[1::2]))


def parse_header(data: bytes) -> int:
    if len(data) < HEADER.size:
        raise PacketError(f"packet too short ({len(data)} B)")
    magic, cmd = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise PacketError(f"bad magic {magic.hex()}")
    return cmd


def parse_report(data: bytes) -> Report:
    if parse_header(data) != CMD_REPORT or len(data) < HEADER.size + 10:
        raise PacketError("not a report packet")
    ip, port, dev = struct.unpack_from(">4sH4s", data, HEADER.size)
    return Report(str(ipaddress.IPv4Address(ip)), port, dev)


def parse_iq(data: bytes, endian: str = "<") -> IQBlock:
    if parse_header(data) != CMD_IQ:
        raise PacketError("not an IQ packet")
    if len(data) != IQ_PACKET_LEN:
        raise PacketError(f"IQ packet is {len(data)} B, expected {IQ_PACKET_LEN}")
    return IQBlock(struct.unpack_from(f"{endian}{2 * IQ_PAIRS}h", data, HEADER.size))


def build_iq_for_test(samples: list[int], endian: str = "<") -> bytes:
    """Radio-side IQ packet, for synthetic tests and offline experiments only."""
    return HEADER.pack(MAGIC, CMD_IQ) + struct.pack(f"{endian}{2 * IQ_PAIRS}h", *samples)


def build_report_for_test(ip: str, port: int, device_id: bytes) -> bytes:
    return HEADER.pack(MAGIC, CMD_REPORT) + struct.pack(
        ">4sH4s", ipaddress.IPv4Address(ip).packed, port, device_id)


# --- Output sinks ----------------------------------------------------------

class IQWriter:
    """Writes I/Q as a stereo 16-bit 48 kHz WAV (I left, Q right) or raw int16 LE."""

    def __init__(self, path: str, fmt: str) -> None:
        self.fmt = fmt
        self._wav: wave.Wave_write | None = None
        self._raw: BinaryIO | None = None
        if fmt == "wav":
            self._wav = wave.open(path, "wb")
            self._wav.setnchannels(2)
            self._wav.setsampwidth(2)
            self._wav.setframerate(SAMPLE_RATE)
        else:
            self._raw = open(path, "wb")

    def write(self, block: IQBlock) -> None:
        data = struct.pack(f"<{len(block.samples)}h", *block.samples)
        if self._wav:
            self._wav.writeframes(data)
        elif self._raw:
            self._raw.write(data)

    def close(self) -> None:
        if self._wav:
            self._wav.close()
        if self._raw:
            self._raw.close()


# --- Session ---------------------------------------------------------------

def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def dry_run(args: argparse.Namespace) -> int:
    print("dry run: no --host given, nothing is sent")
    print(f"discover  -> :{RADIO_PORT}  {hexdump(build_discover(args.pc_ip, args.local_port))}")
    print(f"heartbeat -> :{RADIO_PORT}  {hexdump(build_heartbeat())}"
          f"   (every {HEARTBEAT_PERIOD_S:g} s)")
    if args.lo is not None:
        print(f"set LO    -> :{RADIO_PORT}  {hexdump(build_set_lo(args.lo))}")
    return 0


def run(args: argparse.Namespace) -> int:
    endian = "<" if args.iq_endian == "little" else ">"
    dest = (args.host, RADIO_PORT)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", args.local_port))
    sock.settimeout(0.5)
    writer = IQWriter(args.output, args.format) if args.output else None
    count = 0
    try:
        sock.sendto(build_discover(args.pc_ip, args.local_port), dest)
        if args.lo is not None:
            sock.sendto(build_set_lo(args.lo), dest)
        start = last_hb = last_rx = time.monotonic()
        while time.monotonic() - start < args.duration:
            if args.packets and count >= args.packets:
                break
            now = time.monotonic()
            if now - last_hb >= HEARTBEAT_PERIOD_S:
                sock.sendto(build_heartbeat(), dest)
                last_hb = now
            try:
                data, peer = sock.recvfrom(2048)
            except socket.timeout:
                if now - last_rx > SESSION_TIMEOUT_S:
                    print("no data for 10 s; re-sending discover", file=sys.stderr)
                    sock.sendto(build_discover(args.pc_ip, args.local_port), dest)
                    last_rx = now
                continue
            if peer[0] != args.host:
                continue
            last_rx = time.monotonic()
            try:
                cmd = parse_header(data)
                if cmd == CMD_REPORT:
                    r = parse_report(data)
                    print(f"report: {r.ip}:{r.port} id {r.device_id.hex()}")
                elif cmd == CMD_IQ:
                    block = parse_iq(data, endian)
                    count += 1
                    if writer:
                        writer.write(block)
                    elif count % 250 == 1:
                        print(f"IQ packet {count}: first pair {block.pairs[0]}")
            except PacketError as exc:
                print(f"ignored packet from {peer[0]}: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        if writer:
            writer.close()
        sock.close()
    print(f"received {count} IQ packets ({count * IQ_PAIRS / SAMPLE_RATE:.2f} s of I/Q)")
    return 0


def lo_hz(text: str) -> int:
    value = int(float(text))
    build_set_lo(value)  # range check
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Receive-only HDSDR/IQ client for the G7250 (dry run unless --host).")
    ap.add_argument("--host", help="radio IPv4; without it nothing is sent")
    ap.add_argument("--local-port", type=int, default=DEFAULT_LOCAL_PORT,
                    help=f"local UDP port to receive on (default {DEFAULT_LOCAL_PORT})")
    ap.add_argument("--pc-ip", default="0.0.0.0",
                    help="IPv4 to announce in discover (default 0.0.0.0 = source address)")
    ap.add_argument("--lo", type=lo_hz, help="set LO in Hz (0.5-108 MHz), e.g. 7074000")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds to receive")
    ap.add_argument("--packets", type=int, default=0, help="stop after N IQ packets")
    ap.add_argument("--output", help="write I/Q to this file")
    ap.add_argument("--format", choices=("wav", "raw"), default="wav",
                    help="wav = stereo 48 kHz int16; raw = interleaved int16 LE")
    ap.add_argument("--iq-endian", choices=("little", "big"), default="little",
                    help="sample byte order on the wire (undocumented; default little)")
    args = ap.parse_args(argv)
    build_discover(args.pc_ip, args.local_port)  # validate before anything else
    return run(args) if args.host else dry_run(args)


if __name__ == "__main__":
    sys.exit(main())
