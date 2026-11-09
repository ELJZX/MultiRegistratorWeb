import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .modbus import ChannelSpec, DeviceSpec, ModbusReader, ModbusReadError
from .models import Device
from .storage import save_sample

logger = logging.getLogger("devices.poller")


def build_spec(device):
    channels = [
        ChannelSpec(
            name=channel.name,
            address=channel.address,
            function=channel.function,
            data_type=channel.data_type,
            scale=channel.scale,
            unit=channel.unit,
            word_order=channel.word_order,
            writable=channel.writable,
        )
        for channel in device.channels.all()
    ]
    return DeviceSpec(
        id=str(device.pk),
        name=device.name,
        host=device.host,
        port=device.port,
        unit_id=device.unit_id,
        poll_interval=device.poll_interval,
        timeout=device.timeout,
        retries=device.retries,
        channels=channels,
    )


def status_payload(device):
    return {
        "device_id": str(device.pk),
        "online": device.online,
        "last_attempt": device.last_attempt.isoformat() if device.last_attempt else None,
        "last_success": device.last_success.isoformat() if device.last_success else None,
        "last_error": device.last_error,
        "latency_ms": device.latency_ms,
        "values": device.latest_values or {},
        "channel_available": device.channel_availability or {},
    }


def poll_device(device, modbus_reader):
    spec = build_spec(device)
    device.last_attempt = timezone.now()
    start = time.perf_counter()
    try:
        result = modbus_reader.read_full(spec)
    except Exception as exc:
        device.online = False
        device.last_error = str(exc)
        device.latency_ms = (time.perf_counter() - start) * 1000.0
        device.save(
            update_fields=["online", "last_error", "latency_ms", "last_attempt", "updated_at"]
        )
        logger.warning("device %s (%s) offline: %s", device.pk, device.host, exc)
        return device

    device.online = True
    device.last_success = timezone.now()
    device.last_error = ""
    device.latency_ms = (time.perf_counter() - start) * 1000.0
    device.latest_values = {name: result.values.get(name) for name in spec.channel_names}
    device.channel_availability = result.available
    device.save(
        update_fields=[
            "online",
            "last_success",
            "last_error",
            "latency_ms",
            "latest_values",
            "channel_availability",
            "last_attempt",
            "updated_at",
        ]
    )
    try:
        save_sample(device, spec, device.last_success, result.values)
    except Exception as exc:
        logger.exception("cannot store sample for device %s: %s", device.pk, exc)
        device.last_error = f"storage: {exc}"
        device.save(update_fields=["last_error", "updated_at"])
    return device


def poll_once(modbus_reader=None):
    owned = modbus_reader is None
    reader = modbus_reader or ModbusReader()
    results = []
    try:
        devices = list(Device.objects.filter(enabled=True).prefetch_related("channels"))
        for device in devices:
            results.append(poll_device(device, reader))
    finally:
        if owned:
            reader.close()
    return results


class Poller:
    def __init__(self, tick=None, reload_interval=None):
        self.tick = tick if tick is not None else settings.POLLER_TICK
        self.reload_interval = (
            reload_interval if reload_interval is not None else settings.POLLER_RELOAD_INTERVAL
        )
        self.reader = ModbusReader()
        self._stop = threading.Event()
        self._devices = {}
        self._next_poll = {}
        self._last_reload = 0.0

    def stop(self):
        self._stop.set()

    def _reload(self):
        close_old_connections()
        loaded = {
            device.pk: device
            for device in Device.objects.filter(enabled=True).prefetch_related("channels")
        }
        for removed in set(self._devices) - set(loaded):
            self.reader.close(str(removed))
            self._next_poll.pop(removed, None)
        now = time.monotonic()
        for pk, device in loaded.items():
            self._next_poll.setdefault(pk, now)
        self._devices = loaded
        self._last_reload = now

    def run(self):
        logger.info("poller started (tick=%ss)", self.tick)
        try:
            while not self._stop.is_set():
                try:
                    now = time.monotonic()
                    if now - self._last_reload >= self.reload_interval:
                        self._reload()
                    did_work = False
                    for pk, device in list(self._devices.items()):
                        if self._stop.is_set():
                            break
                        if now >= self._next_poll.get(pk, 0.0):
                            try:
                                poll_device(device, self.reader)
                            except Exception:
                                logger.exception("unexpected poll failure for device %s", pk)
                            self._next_poll[pk] = time.monotonic() + max(
                                0.1, device.poll_interval
                            )
                            did_work = True
                    if not did_work:
                        self._stop.wait(self.tick)
                except Exception:
                    logger.exception("poller loop error")
                    self._stop.wait(max(self.tick, 1.0))
        finally:
            self.reader.close()
            close_old_connections()
            logger.info("poller stopped")
