import random
import time

from django.core.management.base import BaseCommand

from devices.modbus import encode_registers
from devices.simulator import ModbusSimulator, TemperatureSource


class Command(BaseCommand):
    help = "Запускает эмулятор Modbus TCP устройства"

    def add_arguments(self, parser):
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", type=int, default=5020)
        parser.add_argument("--interval", type=float, default=1.0)
        parser.add_argument("--base-temp", type=float, default=25.0)
        parser.add_argument("--amplitude", type=float, default=5.0)
        parser.add_argument("--step", type=float, default=0.4)
        parser.add_argument("--seed", type=int, default=None)

    def handle(self, *args, **options):
        simulator = ModbusSimulator(options["host"], options["port"])
        temperature = TemperatureSource(
            base=options["base_temp"],
            amplitude=options["amplitude"],
            step=options["step"],
            rng=random.Random(options["seed"]),
        )
        humidity_rng = random.Random(None if options["seed"] is None else options["seed"] + 1)
        counter = 0

        try:
            simulator.start()
        except OSError as exc:
            self.stderr.write(f"Не удалось занять {options['host']}:{options['port']}: {exc}")
            return

        self.stdout.write("=" * 58)
        self.stdout.write(" Эмулятор устройства MultiRegistrator (Modbus TCP)")
        self.stdout.write("=" * 58)
        self.stdout.write(f" Адрес: {options['host']}:{options['port']}")
        self.stdout.write(" Карта регистров:")
        self.stdout.write("   holding  1  float32  temperature")
        self.stdout.write("   holding  3  uint16   humidity (scale 0.1, %)")
        self.stdout.write("   holding  4  uint16   counter")
        self.stdout.write("   coil     1  bool     relay")
        self.stdout.write("=" * 58)

        try:
            while True:
                value = temperature.next()
                humidity = round(humidity_rng.uniform(30.0, 70.0), 1)
                counter = (counter + 1) & 0xFFFF

                simulator.set_holding(1, encode_registers(value, "float32"))
                simulator.set_holding(3, encode_registers(humidity, "uint16", scale=0.1))
                simulator.set_holding(4, counter)
                simulator.set_coil(1, counter % 2 == 1)

                self.stdout.write(
                    f"[{time.strftime('%H:%M:%S')}] temperature={value:6.2f} C  "
                    f"humidity={humidity:5.1f} %  counter={counter:5d}  "
                    f"connections={simulator.connections}"
                )
                time.sleep(max(0.01, options["interval"]))
        except KeyboardInterrupt:
            self.stdout.write("Остановка эмулятора...")
        finally:
            simulator.stop()
