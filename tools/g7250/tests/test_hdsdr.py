"""Synthetic-vector tests for the HDSDR/IQ client (no network traffic)."""
from __future__ import annotations

import contextlib
import io
import os
import struct
import tempfile
import unittest
import wave

from g7250 import hdsdr_client as h


class BuildTests(unittest.TestCase):
    def test_discover(self) -> None:
        pkt = h.build_discover("192.168.1.20", 50001)
        self.assertEqual(pkt, bytes.fromhex("AA5555AA 0101 C0A80114 C351"))

    def test_discover_zero_ip(self) -> None:
        self.assertEqual(h.build_discover()[6:10], b"\x00\x00\x00\x00")

    def test_heartbeat(self) -> None:
        self.assertEqual(h.build_heartbeat(), bytes.fromhex("AA5555AA0102"))

    def test_set_lo(self) -> None:
        pkt = h.build_set_lo(7_074_000)
        self.assertEqual(pkt[:6], bytes.fromhex("AA5555AA0103"))
        self.assertEqual(struct.unpack(">Q", pkt[6:])[0], 7_074_000)

    def test_set_lo_range(self) -> None:
        h.build_set_lo(h.LO_MIN_HZ)
        h.build_set_lo(h.LO_MAX_HZ)
        for bad in (h.LO_MIN_HZ - 1, h.LO_MAX_HZ + 1):
            with self.assertRaises(ValueError):
                h.build_set_lo(bad)

    def test_only_pc_commands_can_be_built(self) -> None:
        for cmd in (h.CMD_REPORT, h.CMD_IQ, 0x0104, 0x0300):
            with self.assertRaises(ValueError):
                h._packet(cmd)


class ParseTests(unittest.TestCase):
    def test_report(self) -> None:
        r = h.parse_report(h.build_report_for_test("10.0.0.5", 50002, b"\x01\x02\x03\x04"))
        self.assertEqual((r.ip, r.port, r.device_id), ("10.0.0.5", 50002, b"\x01\x02\x03\x04"))

    def test_iq_round_trip(self) -> None:
        samples = [(i * 97) % 65536 - 32768 for i in range(2 * h.IQ_PAIRS)]
        pkt = h.build_iq_for_test(samples)
        self.assertEqual(len(pkt), h.IQ_PACKET_LEN)
        block = h.parse_iq(pkt)
        self.assertEqual(list(block.samples), samples)
        self.assertEqual(block.pairs[1], (samples[2], samples[3]))
        self.assertEqual(list(h.parse_iq(h.build_iq_for_test(samples, ">"), ">").samples),
                         samples)

    def test_bad_packets(self) -> None:
        with self.assertRaises(h.PacketError):
            h.parse_header(b"\xAA\x55")
        with self.assertRaises(h.PacketError):
            h.parse_header(bytes.fromhex("AA55AA550202"))
        with self.assertRaises(h.PacketError):
            h.parse_iq(h.build_iq_for_test([0] * 384)[:-2])
        with self.assertRaises(h.PacketError):
            h.parse_report(h.build_heartbeat())


class OutputTests(unittest.TestCase):
    def test_wav_and_raw(self) -> None:
        samples = list(range(-192, 192))
        block = h.parse_iq(h.build_iq_for_test(samples))
        with tempfile.TemporaryDirectory() as tmp:
            wav_path, raw_path = os.path.join(tmp, "iq.wav"), os.path.join(tmp, "iq.raw")
            for path, fmt in ((wav_path, "wav"), (raw_path, "raw")):
                w = h.IQWriter(path, fmt)
                w.write(block)
                w.close()
            with wave.open(wav_path, "rb") as wf:
                self.assertEqual((wf.getnchannels(), wf.getsampwidth(), wf.getframerate()),
                                 (2, 2, 48_000))
                self.assertEqual(wf.getnframes(), h.IQ_PAIRS)
            with open(raw_path, "rb") as fh:
                self.assertEqual(list(struct.unpack("<384h", fh.read())), samples)

    def test_dry_run_sends_nothing(self) -> None:
        def no_socket(*_a: object, **_k: object) -> None:
            raise AssertionError("socket opened in dry-run mode")

        orig = h.socket.socket
        h.socket.socket = no_socket  # type: ignore[assignment]
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(h.main(["--lo", "7074000"]), 0)
        finally:
            h.socket.socket = orig  # type: ignore[assignment]
        self.assertIn("dry run", buf.getvalue())
        self.assertIn("AA 55 55 AA 01 03", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
