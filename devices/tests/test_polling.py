from django.test import TestCase

from devices.modbus import ReadResult
from devices.models import Measurement
from devices.polling import poll_device

from .test_models_storage import make_device


class FakeReader:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def read_full(self, spec):
        if self.error:
            raise self.error
        return self.result


class PollingTests(TestCase):
    def setUp(self):
        self.device = make_device()

    def test_poll_success_saves_measurement(self):
        reader = FakeReader(ReadResult(values={"temperature": 24.0}, unavailable=set()))
        device = poll_device(self.device, reader)
        self.assertTrue(device.online)
        self.assertEqual(device.latest_values["temperature"], 24.0)
        self.assertEqual(Measurement.objects.count(), 1)

    def test_poll_failure_marks_offline(self):
        reader = FakeReader(error=RuntimeError("timeout"))
        device = poll_device(self.device, reader)
        self.assertFalse(device.online)
        self.assertIn("timeout", device.last_error)
        self.assertEqual(Measurement.objects.count(), 0)
