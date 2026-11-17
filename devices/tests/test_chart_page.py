from datetime import datetime

from django.contrib.staticfiles import finders
from django.test import TestCase

from .test_models_storage import make_device


class ChartPageTests(TestCase):
    def setUp(self):
        self.device = make_device()
        self.url = f"/devices/{self.device.pk}/"

    def test_default_period_is_one_minute(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        start = datetime.fromisoformat(response.context["default_start"])
        end = datetime.fromisoformat(response.context["default_end"])
        span = (end - start).total_seconds()
        self.assertGreaterEqual(span, 59)
        self.assertLessEqual(span, 61)

    def test_chart_utils_loaded_before_chart(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn("devices/chart-utils", content)
        self.assertIn("devices/chart.", content)
        self.assertLess(
            content.index("devices/chart-utils"),
            content.index("devices/chart."),
        )

    def test_period_inputs_present(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="period-start"')
        self.assertContains(response, 'id="period-end"')


class ChartUtilsTests(TestCase):
    def test_utils_file_exists(self):
        self.assertIsNotNone(finders.find("devices/chart-utils.js"))
