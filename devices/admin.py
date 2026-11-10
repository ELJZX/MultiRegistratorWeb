from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from .discovery import discover_channels, find_unit_ids
from .modbus import ModbusReadError, ModbusReader, RegisterFunction
from .models import Channel, Device, Measurement, UserEventLog
from .polling import build_spec


def _as_int(raw, default, minimum=0, maximum=65535):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _as_float(raw, default):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


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
        "scan_link",
    )
    list_filter = ("enabled", "online")
    search_fields = ("name", "host")
    inlines = [ChannelInline]
    change_form_template = "admin/devices/device/change_form.html"
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

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/scan/",
                self.admin_site.admin_view(self.scan_channels_view),
                name="devices_device_scan",
            ),
        ]
        return custom + urls

    @admin.display(description="Сканирование")
    def scan_link(self, obj):
        url = reverse("admin:devices_device_scan", args=[obj.pk])
        return format_html('<a class="button" href="{}">Сканировать</a>', url)

    def _add_scanned_channels(self, request, device):
        created = 0
        for key in request.POST.getlist("selected"):
            try:
                function, address, word_order = key.rsplit("-", 2)
                address = int(address)
            except (ValueError, TypeError):
                continue
            if function not in (
                RegisterFunction.HOLDING.value,
                RegisterFunction.INPUT.value,
                RegisterFunction.COIL.value,
                RegisterFunction.DISCRETE.value,
            ):
                continue
            if word_order not in ("big", "little"):
                word_order = "big"
            name = (request.POST.get("name_" + key) or "").strip() or f"канал {address}"
            Channel.objects.update_or_create(
                device=device,
                name=name,
                defaults={
                    "address": address,
                    "function": function,
                    "data_type": "float32",
                    "scale": 1.0,
                    "unit": "",
                    "word_order": word_order,
                    "order": address,
                },
            )
            created += 1
        return created

    def scan_channels_view(self, request, object_id):
        device = get_object_or_404(self.model, pk=object_id)
        candidates = []
        unit_ids = []
        error = ""
        form_data = {
            "function": request.POST.get("function", "both"),
            "start": request.POST.get("start", "0"),
            "end": request.POST.get("end", "64"),
            "min_abs": request.POST.get("min_abs", "0.001"),
            "max_abs": request.POST.get("max_abs", "1000000"),
            "unit_start": request.POST.get("unit_start", "1"),
            "unit_end": request.POST.get("unit_end", "32"),
        }

        if request.method == "POST":
            apply_unit = request.POST.get("apply_unit")
            if apply_unit:
                try:
                    device.unit_id = _as_int(apply_unit, device.unit_id, 0, 255)
                    device.save(update_fields=["unit_id", "updated_at"])
                    self.message_user(
                        request,
                        f"Modbus ID установлен: {device.unit_id}",
                        messages.SUCCESS,
                    )
                except Exception:
                    self.message_user(request, "Не удалось установить Modbus ID.", messages.ERROR)
                return redirect("admin:devices_device_change", device.pk)

            action = request.POST.get("action", "")
            if action == "add":
                created = self._add_scanned_channels(request, device)
                self.message_user(
                    request, f"Добавлено каналов: {created}", messages.SUCCESS
                )
                return redirect("admin:devices_device_change", device.pk)

            reader = ModbusReader()
            try:
                spec = build_spec(device)
                if action == "find_unit":
                    start = _as_int(form_data["unit_start"], 1, 0, 255)
                    end = _as_int(form_data["unit_end"], start + 31, start, 255)
                    unit_ids = find_unit_ids(reader, spec, start, end)
                elif action == "scan":
                    start = _as_int(form_data["start"], 0, 0, 65535)
                    end = _as_int(form_data["end"], start + 64, start + 1, 65535)
                    if end - start > 512:
                        end = start + 512
                        error = "Диапазон ограничен 512 регистрами."
                    min_abs = _as_float(form_data["min_abs"], 1e-3)
                    max_abs = _as_float(form_data["max_abs"], 1e6)
                    if form_data["function"] == "both":
                        functions = ["holding", "input"]
                    else:
                        functions = [form_data["function"]]
                    for function in functions:
                        candidates.extend(
                            discover_channels(
                                reader, spec, function, start, end, min_abs, max_abs
                            )
                        )
            except ModbusReadError as exc:
                error = str(exc)
            except Exception as exc:  # pragma: no cover - defensive
                error = f"Ошибка сканирования: {exc}"
            finally:
                reader.close()

        context = dict(
            self.admin_site.each_context(request),
            opts=self.model._meta,
            original=device,
            title="Поиск и сканирование каналов",
            candidates=candidates,
            unit_ids=unit_ids,
            error=error,
            form_data=form_data,
        )
        return render(request, "admin/devices/device/scan.html", context)


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


@admin.register(UserEventLog)
class UserEventLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "username",
        "action",
        "device",
        "description",
        "ip_address",
        "status_code",
        "duration_ms",
    )
    list_filter = ("action", "created_at")
    search_fields = ("username", "description", "path", "ip_address", "device__name")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("device", "user")
    readonly_fields = tuple(field.name for field in UserEventLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True
