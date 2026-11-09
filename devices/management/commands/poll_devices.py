import signal

from django.core.management.base import BaseCommand

from devices.polling import Poller, poll_once


class Command(BaseCommand):
    help = "Опрашивает Modbus TCP устройства и сохраняет измерения"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Выполнить один цикл опроса и выйти")

    def handle(self, *args, **options):
        if options["once"]:
            devices = poll_once()
            for device in devices:
                state = "online" if device.online else "offline"
                self.stdout.write(f"{device.name} ({device.host}): {state}")
            return

        poller = Poller()

        def _stop(signum, frame):
            poller.stop()

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
        self.stdout.write("Опрос запущен. Для остановки нажмите Ctrl+C.")
        poller.run()
