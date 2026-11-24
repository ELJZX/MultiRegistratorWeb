from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from devices.models import Measurement

from .test_models_storage import make_device


class ApiTests(TestCase):
    def setUp(self):
        self.device = make_device()
        self.now = timezone.now()
        Measurement.objects.create(
            device=self.device,
            channel="temperature",
            value=22.5,
            measured_at=self.now,
        )
        self.user = get_user_model().objects.create_user(
            username="viewer", password="pass12345"
        )
        self.client.force_login(self.user)

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_ready(self):
        response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")

    def test_ready_returns_503_when_database_is_unavailable(self):
        with self.assertLogs("devices.health", level="ERROR"):
            with mock.patch(
                "devices.views.connection.cursor", side_effect=RuntimeError("db down")
            ):
                response = self.client.get("/api/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["database"], "unavailable")

    def test_info(self):
        response = self.client.get("/api/info")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device_count"], 1)

    def test_device_list(self):
        response = self.client.get("/api/devices")
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["config"]["name"], self.device.name)
        self.assertIn("status", payload[0])

    def test_device_by_host(self):
        response = self.client.get(f"/api/devices/{self.device.host}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["config"]["id"], str(self.device.pk))

    def test_latest(self):
        response = self.client.get(f"/api/devices/{self.device.pk}/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device_id"], str(self.device.pk))

    def test_channels(self):
        response = self.client.get(f"/api/devices/{self.device.pk}/channels")
        payload = response.json()
        self.assertEqual(payload["channels"], ["temperature"])

    def test_dates(self):
        response = self.client.get(f"/api/devices/{self.device.pk}/dates")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["dates"]), 1)

    def test_data(self):
        start = (self.now - timedelta(hours=1)).isoformat()
        end = (self.now + timedelta(hours=1)).isoformat()
        response = self.client.get(
            f"/api/devices/{self.device.pk}/data", {"start": start, "end": end}
        )
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["channels"]["temperature"]["values"], [22.5])

    def test_unknown_device(self):
        response = self.client.get("/api/devices/9999/latest")
        self.assertEqual(response.status_code, 404)

    def test_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.device.name)

    def test_device_page(self):
        response = self.client.get(f"/devices/{self.device.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temperature")
        self.assertContains(response, 'step="1"')
        self.assertContains(response, "chartjs-plugin-zoom")
        self.assertRegex(response.content.decode(), r"\d{2}:\d{2}:\d{2}")
