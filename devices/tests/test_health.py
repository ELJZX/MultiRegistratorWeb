from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from devices.models import PollerHeartbeat
from devices.polling import update_heartbeat


class PollerHealthTests(TestCase):
    def test_update_heartbeat_keeps_one_row(self):
        update_heartbeat()
        update_heartbeat()
        self.assertEqual(PollerHeartbeat.objects.count(), 1)
        self.assertIsNotNone(PollerHeartbeat.objects.get(pk=1).last_seen)

    def test_fresh_heartbeat_passes(self):
        update_heartbeat()
        call_command("poller_health", max_age=60, stdout=StringIO())

    def test_stale_heartbeat_fails(self):
        update_heartbeat()
        PollerHeartbeat.objects.filter(pk=1).update(
            last_seen=timezone.now() - timedelta(minutes=5)
        )
        with self.assertRaises(CommandError):
            call_command("poller_health", max_age=60, stdout=StringIO())

    def test_missing_heartbeat_fails(self):
        with self.assertRaises(CommandError):
            call_command("poller_health", max_age=60, stdout=StringIO())
