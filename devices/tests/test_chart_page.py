from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase

from .test_models_storage import make_device


class ChartPageTests(TestCase):
    def setUp(self):
        self.device = make_device()
        self.url = f"/devices/{self.device.pk}/"
        self.user = get_user_model().objects.create_user(
            username="viewer", password="pass12345"
        )
        self.client.force_login(self.user)

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


class PermissionsTests(TestCase):
    def setUp(self):
        self.device = make_device()
        self.viewer = get_user_model().objects.create_user(
            username="viewer", password="pass12345"
        )
        self.staff = get_user_model().objects.create_user(
            username="operator", password="pass12345", is_staff=True
        )

    def test_anonymous_redirected_from_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_anonymous_redirected_from_device_page(self):
        response = self.client.get(f"/devices/{self.device.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_viewer_can_open_dashboard_and_device(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/devices/{self.device.pk}/").status_code, 200
        )

    def test_viewer_sees_no_edit_button_and_no_admin_link(self):
        self.client.force_login(self.viewer)
        content = self.client.get("/").content.decode()
        self.assertIn('<span class="username">viewer</span>', content)
        self.assertNotIn('class="username is-admin"', content)
        self.assertNotIn("Изменить", content)
        self.assertNotIn('href="/admin/"', content)

    def test_viewer_cannot_access_admin(self):
        self.client.force_login(self.viewer)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_sees_edit_button_and_admin_link(self):
        self.client.force_login(self.staff)
        content = self.client.get("/").content.decode()
        self.assertIn('class="username is-admin"', content)
        self.assertIn('href="/admin/"', content)
        self.assertIn("Изменить", content)

    def test_staff_can_access_admin(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_login_page_available_for_anonymous(self):
        self.assertEqual(self.client.get("/login/").status_code, 200)
