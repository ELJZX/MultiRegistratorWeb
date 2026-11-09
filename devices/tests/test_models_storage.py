import tempfile
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from devices import storage
from devices.models import Channel, Device, Measurement


def make_device(**kwargs):
    defaults = {"name": "Test", "host": "127.0.0.1", "port": 5020, "unit_id": 1}
    defaults.update(kwargs)
    device = Device.objects.create(**defaults)
    Channel.objects.create(
        device=device, name="temperature", address=1, data_type="float32", unit="C"
    )
    return device


class ModelTests(TestCase):
    def test_channel_properties(self):
        device = make_device()
        channel = device.channels.first()
        self.assertEqual(channel.word_count, 2)
        self.assertFalse(channel.is_bit)
        coil = Channel.objects.create(
            device=device, name="relay", address=1, function="coil", data_type="uint16"
        )
        self.assertTrue(coil.is_bit)
        self.assertEqual(coil.word_count, 1)

    def test_device_str(self):
        device = make_device(name="Boiler", host="10.0.0.1")
        self.assertIn("Boiler", str(device))
        self.assertIn("10.0.0.1", str(device))


class StorageTests(TestCase):
    def test_database_roundtrip(self):
        device = make_device()
        now = timezone.now()
        Measurement.objects.create(
            device=device, channel="temperature", value=21.5, measured_at=now
        )
        series = storage.read_range(device, now - timedelta(minutes=1), now + timedelta(minutes=1))
        self.assertIn("temperature", series)
        self.assertEqual(series["temperature"].values, [21.5])
        self.assertEqual(len(storage.list_dates(device)), 1)

    @override_settings(ARCHIVE_STORAGE="files")
    def test_file_roundtrip(self):
        device = make_device(host="192.168.1.10")
        now = timezone.now()
        from devices.polling import build_spec

        with tempfile.TemporaryDirectory() as tmp:
            try:
                with override_settings(ARCHIVE_DIR=tmp):
                    storage._writer = None
                    storage._reader = None
                    storage.save_sample(
                        device, build_spec(device), now, {"temperature": 30.0}
                    )
                    series = storage.read_range(
                        device, now - timedelta(minutes=1), now + timedelta(minutes=1)
                    )
                    self.assertIn("temperature", series)
                    self.assertEqual(series["temperature"].values, [30.0])
                    self.assertEqual(storage.list_channels(device), ["temperature"])
                    self.assertTrue(storage.reader().archive_dir.exists())
            finally:
                storage._writer = None
                storage._reader = None
