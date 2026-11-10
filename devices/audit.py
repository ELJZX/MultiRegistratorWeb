import ipaddress
import logging

from django.conf import settings

from .models import UserEventLog

logger = logging.getLogger("devices.audit")


def _client_ip(request):
    if request is None:
        return None
    meta = getattr(request, "META", {}) or {}
    forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
    raw = forwarded.split(",")[0].strip() if forwarded else meta.get("REMOTE_ADDR", "")
    if not raw:
        return None
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        return None
    return raw


def log_event(
    action,
    request=None,
    user=None,
    username="",
    device=None,
    description="",
    details=None,
    status_code=None,
    duration_ms=None,
):
    if not getattr(settings, "AUDIT_LOG_ENABLED", True):
        return None

    if user is None and request is not None:
        candidate = getattr(request, "user", None)
        if candidate is not None and getattr(candidate, "is_authenticated", False):
            user = candidate
    if user is not None and not getattr(user, "is_authenticated", True):
        user = None
    if not username and user is not None:
        username = user.get_username()

    meta = (getattr(request, "META", {}) or {}) if request is not None else {}
    try:
        return UserEventLog.objects.create(
            user=user,
            username=str(username or "")[:150],
            action=action,
            device=device,
            description=str(description or ""),
            details=details or {},
            ip_address=_client_ip(request),
            user_agent=str(meta.get("HTTP_USER_AGENT", "") or "")[:512],
            path=str(getattr(request, "path", "") or "")[:512] if request is not None else "",
            method=str(getattr(request, "method", "") or "")[:10] if request is not None else "",
            status_code=status_code,
            duration_ms=duration_ms,
        )
    except Exception:
        logger.exception("cannot write user event log")
        return None
