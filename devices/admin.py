from django.contrib import admin

from .models import Channel, Device, Measurement


class ChannelInline(admin.TabularInline):
    model = Channel
    extra = 1
    fields = (
        "name",
        "address",
        "function",
        "data_type",
        "scale",
        "unit",
        "word_order",
        "writable",
        "order",
    )


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "host",
        "port",
        "unit_id",
        "enabled",
        "online",
        "last_success",
        "latency_ms",
    )
    list_filter = ("enabled", "online")
    search_fields = ("name", "host")
    inlines = [ChannelInline]
    readonly_fields = (
        "online",
        "last_attempt",
        "last_success",
        "last_error",
        "latency_ms",
        "latest_values",
        "channel_availability",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("name", "host", "port", "unit_id", "enabled")}),
        ("Опрос", {"fields": ("poll_interval", "timeout", "retries")}),
        (
            "Состояние",
            {
                "fields": (
                    "online",
                    "last_attempt",
                    "last_success",
                    "last_error",
                    "latency_ms",
                    "latest_values",
                    "channel_availability",
                )
            },
        ),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    list_display = ("device", "channel", "value", "measured_at")
    list_filter = ("channel",)
    search_fields = ("channel", "device__name", "device__host")
    date_hierarchy = "measured_at"
    readonly_fields = ("device", "channel", "value", "measured_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
