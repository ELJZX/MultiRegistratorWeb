import re
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from .archive import ArchiveReader, ArchiveWriter, TimeSeries
from .models import Measurement

_writer = None
_reader = None


def archive_dir():
    return settings.ARCHIVE_DIR


def writer():
    global _writer
    if _writer is None:
        _writer = ArchiveWriter(archive_dir())
    return _writer


def reader():
    global _reader
    if _reader is None:
        _reader = ArchiveReader(archive_dir())
    return _reader


def uses_files():
    return settings.ARCHIVE_STORAGE in ("files", "both")


def uses_database():
    return settings.ARCHIVE_STORAGE in ("database", "both")


def save_sample(device, spec, timestamp, values):
    if uses_files():
        local = timezone.localtime(timestamp).replace(tzinfo=None)
        writer().append_sample(spec, local, values)
    if uses_database():
        rows = [
            Measurement(
                device=device,
                channel=channel,
                value=None if value is None else float(value),
                measured_at=timestamp,
            )
            for channel, value in values.items()
        ]
        if rows:
            Measurement.objects.bulk_create(rows, batch_size=500)


def list_dates(device):
    if uses_database():
        rows = (
            Measurement.objects.filter(device=device)
            .dates("measured_at", kind="day")
            .order_by("measured_at")
        )
        return sorted({row for row in rows})
    return reader().list_dates(device.host)


def list_channels(device):
    names = [c.name for c in device.channels.all()]
    if names:
        return names
    if uses_database():
        rows = (
            Measurement.objects.filter(device=device)
            .values_list("channel", flat=True)
            .distinct()
            .order_by("channel")
        )
        return list(rows)
    return reader().list_channels(device.host)


def read_range(device, start, end, channels=None):
    if uses_database():
        queryset = Measurement.objects.filter(
            device=device, measured_at__gte=start, measured_at__lte=end
        )
        if channels:
            queryset = queryset.filter(channel__in=channels)
        queryset = queryset.order_by("measured_at")
        result = {}
        if channels:
            for channel in channels:
                result.setdefault(channel, TimeSeries(channel=channel))
        for item in queryset.iterator(chunk_size=5000):
            series = result.setdefault(item.channel, TimeSeries(channel=item.channel))
            series.add(item.measured_at, item.value)
        return result

    local_start = timezone.localtime(start).replace(tzinfo=None)
    local_end = timezone.localtime(end).replace(tzinfo=None)
    raw = reader().read_range(device.host, local_start, local_end, channels)
    result = {}
    for channel, series in raw.items():
        converted = TimeSeries(channel=channel)
        for timestamp, value in zip(series.times, series.values):
            converted.add(timezone.make_aware(timestamp, timezone.get_current_timezone()), value)
        result[channel] = converted
    return result


def parse_datetime(value, default=None):
    if not value:
        return default
    value = value.strip().replace("Z", "+00:00")
    value = re.sub(r" (\d{2}:\d{2})$", r"+\1", value)
    parsed = datetime.fromisoformat(value)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed
