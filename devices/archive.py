import csv
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def sanitize_name(value):
    return "".join(char if char in _ALLOWED else "_" for char in str(value))


def device_folder(archive_dir, host):
    return Path(archive_dir) / sanitize_name(host)


def archive_file_path(archive_dir, host, day):
    if isinstance(day, datetime):
        day = day.date()
    elif isinstance(day, str):
        day = date.fromisoformat(day)
    name = f"{sanitize_name(host)}_{day.isoformat()}.txt"
    return device_folder(archive_dir, host) / name


def format_timestamp(value):
    return value.replace(tzinfo=None).isoformat(sep=" ", timespec="milliseconds")


def parse_timestamp(value):
    value = value.strip()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")


@dataclass
class TimeSeries:
    channel: str
    times: list = field(default_factory=list)
    values: list = field(default_factory=list)

    def add(self, timestamp, value):
        self.times.append(timestamp)
        self.values.append(value)

    def numeric(self):
        times = []
        values = []
        for timestamp, value in zip(self.times, self.values):
            if value is None:
                continue
            times.append(timestamp)
            values.append(value)
        return times, values


class ArchiveWriter:
    def __init__(self, archive_dir):
        self.archive_dir = Path(archive_dir)
        self._locks = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, key):
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    @staticmethod
    def channel_names(device, values):
        names = device.channel_names
        if names:
            return names
        return sorted(values.keys())

    def append_sample(self, device, timestamp, values, channels=None):
        channel_list = list(channels) if channels is not None else self.channel_names(device, values)
        path = archive_file_path(self.archive_dir, device.host, timestamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._lock_for(str(path))
        with lock:
            is_new = not path.exists() or path.stat().st_size == 0
            with path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                if is_new:
                    writer.writerow(["timestamp", *channel_list])
                row = [format_timestamp(timestamp)]
                for channel in channel_list:
                    value = values.get(channel)
                    row.append("" if value is None else repr(float(value)))
                writer.writerow(row)
        return path


class ArchiveReader:
    def __init__(self, archive_dir):
        self.archive_dir = Path(archive_dir)

    def list_devices(self):
        if not self.archive_dir.exists():
            return []
        return sorted(p.name for p in self.archive_dir.iterdir() if p.is_dir())

    def list_dates(self, host):
        folder = device_folder(self.archive_dir, host)
        if not folder.exists():
            return []
        prefix = f"{sanitize_name(host)}_"
        dates = []
        for path in folder.glob(f"{prefix}*.txt"):
            stem = path.stem[len(prefix):]
            try:
                dates.append(date.fromisoformat(stem))
            except ValueError:
                continue
        return sorted(set(dates))

    def list_channels(self, host):
        folder = device_folder(self.archive_dir, host)
        if not folder.exists():
            return []
        files = sorted(folder.glob("*.txt"))
        if not files:
            return []
        with files[-1].open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), None)
        if not header or len(header) < 2:
            return []
        return header[1:]

    def _files_in_range(self, host, start, end):
        folder = device_folder(self.archive_dir, host)
        if not folder.exists():
            return []
        prefix = f"{sanitize_name(host)}_"
        selected = []
        for path in folder.glob(f"{prefix}*.txt"):
            stem = path.stem[len(prefix):]
            try:
                day = date.fromisoformat(stem)
            except ValueError:
                continue
            if start.date() <= day <= end.date():
                selected.append(path)
        return sorted(selected)

    def read_range(self, host, start, end, channels=None):
        files = self._files_in_range(host, start, end)
        result = {}
        available = []

        for path in files:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
                if not header or len(header) < 2:
                    continue
                names = header[1:]
                if not available:
                    available = names
                    for channel in (channels if channels is not None else names):
                        result.setdefault(channel, TimeSeries(channel=channel))
                wanted = available if channels is None else [c for c in channels if c in available]
                index = {name: i + 1 for i, name in enumerate(names)}
                for row in reader:
                    if not row:
                        continue
                    try:
                        timestamp = parse_timestamp(row[0])
                    except (ValueError, IndexError):
                        continue
                    if timestamp < start or timestamp > end:
                        continue
                    for channel in wanted:
                        pos = index[channel]
                        raw = row[pos] if pos < len(row) else ""
                        try:
                            value = float(raw) if raw != "" else None
                        except ValueError:
                            value = None
                        result[channel].add(timestamp, value)

        if channels is not None:
            for channel in channels:
                result.setdefault(channel, TimeSeries(channel=channel))
        return result
