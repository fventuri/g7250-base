"""Synthetic-vector tests for the inter-MCU codec (no hardware involved)."""
from __future__ import annotations

import struct
import unittest

from g7250 import slip


def csv_dir_available() -> bool:
    try:
        slip.find_csv_dir()
        return True
    except FileNotFoundError:
        return False


class SlipTests(unittest.TestCase):
    def test_escapes(self) -> None:
        self.assertEqual(slip.slip_encode(b"\xC0"), b"\xDB\xDC\xC0")
        self.assertEqual(slip.slip_encode(b"\xDB"), b"\xDB\xDD\xC0")
        self.assertEqual(slip.slip_encode(b"\x01\x02"), b"\x01\x02\xC0")

    def test_no_leading_end(self) -> None:
        self.assertNotEqual(slip.slip_encode(b"\x00")[0], slip.END)

    def test_round_trip_all_bytes(self) -> None:
        data = bytes(range(256)) + b"\xC0\xDB\xDB\xC0\xDC\xDD"
        enc = slip.slip_encode(data)
        self.assertEqual(enc.count(slip.END), 1)
        self.assertEqual(slip.slip_decode_stream(enc), [data])

    def test_leading_and_repeated_end_tolerated(self) -> None:
        a, b = b"\xC0abc", b"x\xDBy"
        stream = b"\xC0\xC0" + slip.slip_encode(a) + b"\xC0" + slip.slip_encode(b)
        self.assertEqual(slip.slip_decode_stream(stream), [a, b])

    def test_streaming_split_across_feeds(self) -> None:
        enc = slip.slip_encode(b"\xC0\xDB\x55")
        dec = slip.SlipDecoder()
        frames = []
        for i in range(len(enc)):
            frames += dec.feed(enc[i:i + 1])
        self.assertEqual(frames, [b"\xC0\xDB\x55"])

    def test_bad_escape(self) -> None:
        with self.assertRaises(slip.SlipError):
            slip.slip_unescape(b"\xDB\x00")


class CrcTests(unittest.TestCase):
    def test_check_value(self) -> None:
        # Catalogue check value for CRC-16/ARC.
        self.assertEqual(slip.crc16_arc(b"123456789"), 0xBB3D)

    def test_empty_and_incremental(self) -> None:
        self.assertEqual(slip.crc16_arc(b""), 0)
        self.assertEqual(slip.crc16_arc(b"6789", slip.crc16_arc(b"12345")), 0xBB3D)

    def test_known_small_vectors(self) -> None:
        self.assertEqual(slip.crc16_arc(b"\x01"), 0xC0C1)
        self.assertEqual(slip.crc16_arc(b"A"), 0x30C0)


class FrameTests(unittest.TestCase):
    def test_request_frame(self) -> None:
        pkt = slip.build_packet(slip.MSG_SLAVE_INFO)
        self.assertEqual(len(pkt), slip.MIN_FRAME_LEN)
        self.assertEqual(pkt[:3], b"\x06\x00\x00")
        self.assertEqual(struct.unpack("<H", pkt[3:])[0], slip.crc16_arc(b"\x06\x00\x00"))

    def test_round_trip_and_crc_error(self) -> None:
        payload = bytes([0xC0, 0xDB, 0x00]) * 10
        wire = slip.build_frame(slip.MSG_NET_STATE, payload)
        (pkt,) = slip.slip_decode_stream(wire)
        frame = slip.parse_packet(pkt)
        self.assertEqual((frame.msg_type, frame.reserved, frame.payload),
                         (0x08, b"\x00\x00", payload))
        bad = bytearray(pkt)
        bad[5] ^= 0x01
        with self.assertRaises(slip.FrameError):
            slip.parse_packet(bytes(bad))
        with self.assertRaises(slip.FrameError):
            slip.parse_packet(b"\x01\x00\x00\x00")

    def test_frame_lengths_match_msg_types_csv(self) -> None:
        # decoded frame = 3-byte header + payload + 2-byte CRC (msg_types.csv frame_len)
        expected = {0x01: 0x1AD, 0x02: 0x16B, 0x03: 0x22D, 0x06: 0x6D, 0x08: 0x33}
        for t, n in expected.items():
            self.assertEqual(len(slip.build_packet(t, bytes(slip.PAYLOAD_LEN[t]))), n)


@unittest.skipUnless(csv_dir_available(), "protocol CSVs not found (set G7250_PROTOCOL_DIR)")
class CsvParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fields = {f.offset: f for f in slip.load_fields(slip.FIELD_CSV[slip.MSG_SETTINGS])}

    def put(self, image: bytearray, offset: int, fmt: str, *values: object) -> None:
        struct.pack_into(fmt, image, offset, *values)

    def test_synthetic_settings_image(self) -> None:
        img = bytearray(slip.PAYLOAD_LEN[slip.MSG_SETTINGS])
        self.put(img, 0x000, "<B", 0xAA)
        self.put(img, 0x024, "<Q", 7_074_000)       # VFO A frequency
        self.put(img, 0x024 + 0x18, "<B", 2)        # VFO A mode = USB
        self.put(img, 0x04C, "<Q", 14_074_000)      # VFO B frequency
        self.put(img, 0x07B, "<B", 42)              # RF gain
        self.put(img, 0x098, "<B", 1)               # selected VFO = B
        self.put(img, 0x154, "<f", 5.0)             # TX power W
        self.put(img, 0x158, "<B", 0x37)            # ack seq
        self.put(img, 0x174, "<I", 0xC0A8010A)      # 192.168.1.10
        self.put(img, 0x180, "<H", 50001)
        self.put(img, 0x182, "<B", 1)               # wfview
        img[0x183:0x183 + 4] = b"user"

        wire = slip.build_frame(slip.MSG_SETTINGS, bytes(img))
        frame = slip.parse_packet(slip.slip_decode_stream(wire)[0])
        out = slip.parse_message(frame)

        name = lambda off: self.fields[off].name  # noqa: E731
        vfo_a = out[name(0x024)]
        self.assertIsInstance(vfo_a, dict)
        freq_key = next(k for k in vfo_a if k.startswith("frequency Hz"))
        mode_key = next(k for k in vfo_a if k.startswith("mode code"))
        self.assertEqual(vfo_a[freq_key], 7_074_000)
        self.assertEqual(vfo_a[mode_key], 2)
        self.assertEqual(out[name(0x04C)][freq_key], 14_074_000)
        self.assertEqual(out[name(0x07B)], 42)
        self.assertEqual(out[name(0x098)], 1)
        self.assertAlmostEqual(out[name(0x154)], 5.0)
        self.assertEqual(out[name(0x158)], 0x37)
        self.assertEqual(slip.ipv4_from_u32(out[name(0x174)]), "192.168.1.10")
        self.assertEqual(out[name(0x180)], 50001)
        self.assertEqual(out[name(0x182)], 1)
        self.assertEqual(out[name(0x183)], "user")

    def test_wrong_payload_length_rejected(self) -> None:
        frame = slip.Frame(slip.MSG_SETTINGS, b"\x00\x00", bytes(10))
        with self.assertRaises(slip.FrameError):
            slip.parse_message(frame)

    def test_spectrum_flag_bits(self) -> None:
        payload = bytearray(slip.PAYLOAD_LEN[slip.MSG_SPECTRUM])
        payload[0] = 145                                 # 0 dB bin
        struct.pack_into("<f", payload, 0x200, -73.0)    # S-meter
        struct.pack_into("<I", payload, 0x220, (1 << 1) | (1 << 7))
        out = slip.parse_message(slip.Frame(slip.MSG_SPECTRUM, b"\0\0", bytes(payload)))
        bits = {k: v for k, v in out.items() if isinstance(v, bool)}
        self.assertTrue(next(v for k, v in bits.items() if k.startswith("transmitting")))
        self.assertTrue(next(v for k, v in bits.items() if k.startswith("network client")))
        self.assertFalse(next(v for k, v in bits.items() if k.startswith("Main powering off")))
        spectrum = next(v for k, v in out.items() if k.startswith("spectrum bins"))
        self.assertEqual(spectrum[0] - 145, 0)

    def test_slave_info_and_net_state(self) -> None:
        info = bytearray(slip.PAYLOAD_LEN[slip.MSG_SLAVE_INFO])
        info[0x08:0x08 + 4] = b"V1.0"
        out = slip.parse_message(slip.Frame(slip.MSG_SLAVE_INFO, b"\0\0", bytes(info)))
        self.assertEqual(next(v for k, v in out.items() if k.startswith("MCU version")), "V1.0")

        rec = bytearray(slip.PAYLOAD_LEN[slip.MSG_NET_STATE])
        rec[0], rec[1] = 3, 9
        struct.pack_into("<I", rec, 0x04, 3_573_000)
        struct.pack_into("<f", rec, 0x29, 10.0)
        out = slip.parse_message(slip.Frame(slip.MSG_NET_STATE, b"\0\0", bytes(rec)))
        self.assertEqual(out["sub-type = 3"], 3)
        self.assertEqual(out["sequence 1..255"], 9)
        self.assertEqual(out["VFO A frequency"], 3_573_000)
        self.assertAlmostEqual(out["TX power f32 (unaligned)"], 10.0)

    def test_calibration_parses(self) -> None:
        cal = bytearray(slip.PAYLOAD_LEN[slip.MSG_CALIBRATION])
        cal[0], cal[0x165] = 10, 0x64
        out = slip.parse_message(slip.Frame(slip.MSG_CALIBRATION, b"\0\0", bytes(cal)))
        self.assertEqual(next(v for k, v in out.items() if k.startswith("layout id")), 10)
        self.assertEqual(next(v for k, v in out.items() if k.startswith("end marker")), 0x64)


if __name__ == "__main__":
    unittest.main()
