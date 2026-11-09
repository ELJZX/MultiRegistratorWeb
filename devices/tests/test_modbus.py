from django.test import SimpleTestCase

from devices.modbus import (
    ChannelSpec,
    build_read_blocks,
    decode_registers,
    encode_registers,
)


class DecodeTests(SimpleTestCase):
    def test_uint16(self):
        self.assertEqual(decode_registers([65535], "uint16"), 65535)

    def test_int16_negative(self):
        self.assertEqual(decode_registers([65535], "int16"), -1)

    def test_float32_big(self):
        words = encode_registers(25.5, "float32")
        self.assertAlmostEqual(decode_registers(words, "float32"), 25.5, places=4)

    def test_float32_little(self):
        words = encode_registers(12.25, "float32", word_order="little")
        self.assertAlmostEqual(
            decode_registers(words, "float32", word_order="little"), 12.25, places=4
        )

    def test_scale(self):
        words = encode_registers(42.5, "uint16", scale=0.1)
        self.assertAlmostEqual(decode_registers(words, "uint16", scale=0.1), 42.5, places=4)

    def test_int32_negative(self):
        words = encode_registers(-123456, "int32")
        self.assertEqual(decode_registers(words, "int32"), -123456)


class BlockTests(SimpleTestCase):
    def test_neighbouring_registers_are_merged(self):
        channels = [
            ChannelSpec("a", 1, data_type="float32"),
            ChannelSpec("b", 3, data_type="uint16"),
            ChannelSpec("c", 4, data_type="uint16"),
        ]
        blocks = build_read_blocks(channels)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].start, 1)
        self.assertEqual(blocks[0].count, 4)

    def test_distant_registers_are_separate(self):
        channels = [
            ChannelSpec("a", 0),
            ChannelSpec("b", 100),
        ]
        blocks = build_read_blocks(channels)
        self.assertEqual(len(blocks), 2)

    def test_different_functions_are_separate(self):
        channels = [
            ChannelSpec("a", 0, function="holding"),
            ChannelSpec("b", 0, function="input"),
            ChannelSpec("c", 0, function="coil"),
        ]
        blocks = build_read_blocks(channels)
        self.assertEqual(len(blocks), 3)
