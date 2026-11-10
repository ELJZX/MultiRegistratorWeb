import logging
import re
import time

from django.conf import settings

from .audit import log_event
from .models import Device, UserEventLog

logger = logging.getLogger("devices.audit")

DEVICE_PATH = re.compile(r"^/devices/(?P<pk>\d+)/?$")
IGNORED_PREFIXES = ("/api/", "/static/", "/media/", "/admin/")


class UserActionLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)
        try:
            self._log_request(request, response, (time.perf_counter() - started) * 1000)
        except Exception:
            logger.exception("cannot log user request")
        return response

    def _log_request(self, request, response, duration_ms):
        if not getattr(settings, "AUDIT_LOG_ENABLED", True):
            return
        if request.method != "GET":
            return
        path = request.path
        if not path or path == "/favicon.ico" or path.startswith(IGNORED_PREFIXES):
            return

        device = None
        match = DEVICE_PATH.match(path)
        if match:
            device = Device.objects.filter(pk=int(match.group("pk"))).first()

        log_event(
            UserEventLog.Action.VIEW,
            request=request,
            device=device,
            description=f"Просмотр страницы {path}",
            details={"query": str(request.META.get("QUERY_STRING", "") or "")[:1000]},
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
