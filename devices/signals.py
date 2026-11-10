from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .audit import log_event
from .models import UserEventLog


@receiver(user_logged_in)
def _log_user_logged_in(sender, request, user, **kwargs):
    log_event(
        UserEventLog.Action.LOGIN,
        request=request,
        user=user,
        description="Вход в систему",
    )


@receiver(user_logged_out)
def _log_user_logged_out(sender, request, user, **kwargs):
    username = user.get_username() if user is not None else ""
    log_event(
        UserEventLog.Action.LOGOUT,
        request=request,
        user=user,
        username=username,
        description="Выход из системы",
    )


@receiver(user_login_failed)
def _log_user_login_failed(sender, credentials, request, **kwargs):
    username = ""
    if isinstance(credentials, dict):
        username = str(credentials.get("username", ""))[:150]
    description = f"Неудачный вход: {username}" if username else "Неудачный вход"
    log_event(
        UserEventLog.Action.LOGIN_FAILED,
        request=request,
        username=username,
        description=description,
    )
