from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("devices/<int:pk>/", views.device_detail, name="device-detail"),
    path("api/health", views.api_health, name="api-health"),
    path("api/info", views.api_info, name="api-info"),
    path("api/devices", views.api_devices, name="api-devices"),
    path("api/devices/<str:device_id>", views.api_device, name="api-device"),
    path("api/devices/<str:device_id>/latest", views.api_latest, name="api-latest"),
    path("api/devices/<str:device_id>/channels", views.api_channels, name="api-channels"),
    path("api/devices/<str:device_id>/dates", views.api_dates, name="api-dates"),
    path("api/devices/<str:device_id>/data", views.api_data, name="api-data"),
    path("api/log/print", views.api_log_print, name="api-log-print"),
]
