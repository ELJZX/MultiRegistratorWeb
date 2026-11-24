from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from devices.models import PollerHeartbeat


class Command(BaseCommand):
    help = "Проверяет свежесть heartbeat процесса poller"

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age",
            type=float,
            default=120.0,
            help="Максимальный возраст heartbeat в секундах",
        )

    def handle(self, *args, **options):
        try:
            heartbeat = PollerHeartbeat.objects.filter(pk=1).first()
        except Exception as exc:
            raise CommandError(f"cannot read poller heartbeat: {exc}") from exc

        if heartbeat is None:
            raise CommandError("poller heartbeat not found")

        age = (timezone.now() - heartbeat.last_seen).total_seconds()
        if age > options["max_age"]:
            raise CommandError(
                f"poller heartbeat is stale: {age:.1f}s > {options['max_age']:.1f}s"
            )
        self.stdout.write(f"poller heartbeat is fresh: {age:.1f}s")
