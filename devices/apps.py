from django.apps import AppConfig


class DevicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "devices"
    verbose_name = "Устройства и измерения"

    def ready(self):
        from . import signals  # noqa: F401
