from datetime import timedelta

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from . import storage
from .models import Device
from .polling import status_payload

VERSION = "1.0.0"


def _device_config(device):
    return {
        "id": str(device.pk),
        "name": device.name,
        "host": device.host,
        "port": device.port,
        "device_id": device.unit_id,
        "enabled": device.enabled,
        "poll_interval": device.poll_interval,
        "timeout": device.timeout,
        "retries": device.retries,
        "registers": [channel.to_dict() for channel in device.channels.all()],
        "channels": [channel.name for channel in device.channels.all()],
    }


def _resolve_device(identifier):
    device = None
    if str(identifier).isdigit():
        device = Device.objects.filter(pk=int(identifier)).first()
    if device is None:
        device = Device.objects.filter(host=identifier).order_by("id").first()
    if device is None:
        raise Http404(f"unknown device {identifier}")
    return device


def dashboard(request):
    devices = Device.objects.prefetch_related("channels").all()
    rows = []
    for device in devices:
        values = device.latest_values or {}
        latest = [
            {"name": channel.name, "value": values.get(channel.name), "unit": channel.unit}
            for channel in device.channels.all()
        ]
        rows.append({"device": device, "latest": latest})
    return render(request, "devices/dashboard.html", {"rows": rows})


def device_detail(request, pk):
    device = get_object_or_404(Device.objects.prefetch_related("channels"), pk=pk)
    channels = list(device.channels.all())
    now = timezone.localtime()
    return render(
        request,
        "devices/device_detail.html",
        {
            "device": device,
            "channels": channels,
            "default_end": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "default_start": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        },
    )


@require_GET
def api_health(request):
    return JsonResponse({"status": "ok", "version": VERSION})


@require_GET
def api_info(request):
    return JsonResponse(
        {
            "name": "MultiRegistrator Web",
            "version": VERSION,
            "device_count": Device.objects.count(),
            "storage": storage.settings.ARCHIVE_STORAGE,
        }
    )


@require_GET
def api_devices(request):
    devices = Device.objects.prefetch_related("channels").all()
    return JsonResponse(
        [
            {"config": _device_config(device), "status": status_payload(device)}
            for device in devices
        ],
        safe=False,
    )


@require_GET
def api_device(request, device_id):
    device = _resolve_device(device_id)
    return JsonResponse(
        {"config": _device_config(device), "status": status_payload(device)}
    )


@require_GET
def api_latest(request, device_id):
    device = _resolve_device(device_id)
    return JsonResponse(status_payload(device))


@require_GET
def api_channels(request, device_id):
    device = _resolve_device(device_id)
    names = [channel.name for channel in device.channels.all()]
    availability = device.channel_availability or {}
    available = [name for name in names if availability.get(name, True)]
    unavailable = [name for name in names if name not in available]
    return JsonResponse(
        {
            "device_id": str(device.pk),
            "host": device.host,
            "channels": available,
            "unavailable": unavailable,
        }
    )


@require_GET
def api_dates(request, device_id):
    device = _resolve_device(device_id)
    dates = storage.list_dates(device)
    payload = []
    for item in dates:
        if hasattr(item, "isoformat"):
            payload.append(item.isoformat())
        else:
            payload.append(str(item))
    return JsonResponse({"device_id": str(device.pk), "dates": sorted(set(payload))})


@require_GET
def api_data(request, device_id):
    device = _resolve_device(device_id)
    end = storage.parse_datetime(request.GET.get("end"), default=timezone.now())
    start = storage.parse_datetime(request.GET.get("start"), default=end - timedelta(hours=24))
    if start > end:
        start, end = end, start
    raw_channels = request.GET.get("channels")
    if raw_channels:
        wanted = [item for item in raw_channels.split(",") if item]
    else:
        wanted = storage.list_channels(device)
    series = storage.read_range(device, start, end, wanted)

    payload = {
        "device_id": str(device.pk),
        "host": device.host,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "channels": {},
    }
    for name, item in series.items():
        payload["channels"][name] = {
            "times": [timestamp.isoformat() for timestamp in item.times],
            "values": item.values,
        }
    return JsonResponse(payload)
