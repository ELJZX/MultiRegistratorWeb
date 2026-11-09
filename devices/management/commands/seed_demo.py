from django.core.management.base import BaseCommand

from devices.models import Channel, Device


class Command(BaseCommand):
    help = "Создаёт демонстрационное устройство с картой регистров эмулятора"

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=5020)
        parser.add_argument("--name", default="Демо-устройство")

    def handle(self, *args, **options):
        device, _ = Device.objects.update_or_create(
            name=options["name"],
            defaults={
                "host": options["host"],
                "port": options["port"],
                "unit_id": 1,
                "enabled": True,
                "poll_interval": 2.0,
                "timeout": 3.0,
                "retries": 1,
            },
        )
        channels = [
            {
                "name": "temperature",
                "address": 1,
                "function": Channel.Function.HOLDING,
                "data_type": Channel.DataType.FLOAT32,
                "scale": 1.0,
                "unit": "°C",
                "order": 1,
            },
            {
                "name": "humidity",
                "address": 3,
                "function": Channel.Function.HOLDING,
                "data_type": Channel.DataType.UINT16,
                "scale": 0.1,
                "unit": "%",
                "order": 2,
            },
            {
                "name": "counter",
                "address": 4,
                "function": Channel.Function.HOLDING,
                "data_type": Channel.DataType.UINT16,
                "scale": 1.0,
                "unit": "",
                "order": 3,
            },
            {
                "name": "relay",
                "address": 1,
                "function": Channel.Function.COIL,
                "data_type": Channel.DataType.UINT16,
                "scale": 1.0,
                "unit": "",
                "order": 4,
            },
        ]
        for spec in channels:
            Channel.objects.update_or_create(
                device=device,
                name=spec["name"],
                defaults={
                    "address": spec["address"],
                    "function": spec["function"],
                    "data_type": spec["data_type"],
                    "scale": spec["scale"],
                    "unit": spec["unit"],
                    "order": spec["order"],
                },
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Демо-устройство готово: {device.name} ({device.host}:{device.port}), "
                f"каналов: {device.channels.count()}"
            )
        )
