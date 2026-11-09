from django.test import SimpleTestCase

from devices.modbus import ChannelSpec, DeviceSpec, ModbusReader, encode_registers
from devices.simulator import ModbusSimulator, TemperatureSource, pack_bits


class SimulatorTests(SimpleTestCase):
    def test_pack_bits(self):
        self.assertEqual(pack_bits([True, False, True]), b"\x05")

    def test_temperature_source_is_bounded(self):
        source = TemperatureSource(base=10, amplitude=1, step=100, rng=None)
        value = source.next()
        self.assertGreaterEqual(value, 9)
        self.assertLessEqual(value, 11)

    def test_reader_against_simulator(self):
        simulator = ModbusSimulator("127.0.0.1", 0).start()
        try:
            simulator.set_holding(1, encode_registers(26.5, "float32"))
            simulator.set_holding(3, encode_registers(55.0, "uint16", scale=0.1))
            simulator.set_coil(1, True)
            host, port = simulator.address
            spec = DeviceSpec(
                id="sim",
                name="sim",
                host=host,
                port=port,
                timeout=2.0,
                channels=[
                    ChannelSpec("temperature", 1, data_type="float32"),
                    ChannelSpec("humidity", 3, data_type="uint16", scale=0.1),
                    ChannelSpec("relay", 1, function="coil"),
                ],
            )
            reader = ModbusReader()
            try:
                result = reader.read_full(spec)
            finally:
                reader.close()
            self.assertAlmostEqual(result.values["temperature"], 26.5, places=3)
            self.assertAlmostEqual(result.values["humidity"], 55.0, places=3)
            self.assertEqual(result.values["relay"], 1.0)
        finally:
            simulator.stop()
