import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from devices.models import Measurement, UserEventLog

from .test_models_storage import make_device


class AuditLogTests(TestCase):
    def setUp(self):
        self.device = make_device()
        self.now = timezone.now()
        Measurement.objects.create(
            device=self.device,
            channel="temperature",
            value=22.0,
            measured_at=self.now,
        )

    def _range(self):
        return {
            "start": (self.now - timedelta(hours=1)).isoformat(),
            "end": (self.now + timedelta(hours=1)).isoformat(),
        }

    def test_page_view_is_logged(self):
        self.client.get("/")
        entry = UserEventLog.objects.get(action=UserEventLog.Action.VIEW, path="/")
        self.assertEqual(entry.status_code, 200)
        self.assertGreaterEqual(entry.duration_ms, 0)

    def test_manual_chart_is_logged(self):
        params = self._range()
        params["reason"] = "manual"
        response = self.client.get(f"/api/devices/{self.device.pk}/data", params)
        self.assertEqual(response.status_code, 200)
        entry = UserEventLog.objects.get(action=UserEventLog.Action.CHART)
        self.assertEqual(entry.device_id, self.device.pk)
        self.assertEqual(entry.details["reason"], "manual")
        self.assertGreaterEqual(entry.details["points"], 1)

    def test_live_chart_is_not_logged(self):
        params = self._range()
        params["reason"] = "live"
        response = self.client.get(f"/api/devices/{self.device.pk}/data", params)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserEventLog.objects.filter(action=UserEventLog.Action.CHART).exists())

    def test_print_action_is_logged(self):
        payload = {
            "device_id": self.device.pk,
            "start": "2026-11-10T10:00:00",
            "end": "2026-11-10T11:00:00",
            "channels": ["temperature"],
        }
        response = self.client.post(
            "/api/log/print",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        entry = UserEventLog.objects.get(action=UserEventLog.Action.PRINT)
        self.assertEqual(entry.device_id, self.device.pk)
        self.assertEqual(entry.details["channels"], ["temperature"])

    def test_login_and_failed_login_are_logged(self):
        get_user_model().objects.create_user(username="operator", password="secret123")
        self.client.post("/login/", {"username": "operator", "password": "secret123"})
        self.assertTrue(
            UserEventLog.objects.filter(
                action=UserEventLog.Action.LOGIN, username="operator"
            ).exists()
        )
        self.client.logout()
        self.assertTrue(
            UserEventLog.objects.filter(
                action=UserEventLog.Action.LOGOUT, username="operator"
            ).exists()
        )
        self.client.post("/login/", {"username": "operator", "password": "bad"})
        self.assertTrue(
            UserEventLog.objects.filter(
                action=UserEventLog.Action.LOGIN_FAILED, username="operator"
            ).exists()
        )
