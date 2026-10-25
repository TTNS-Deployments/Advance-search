"""Demo sign-in: one shared password plus a choice of role (Admin or User).

This is for demos only. Entra ID sign-in with real roles is on the roadmap (README, Status and roadmap).
"""

import hmac
import logging
from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .roles import ALL_ROLES, ROLE_DESCRIPTIONS, User

log = logging.getLogger(__name__)


def _safe_next(request, url: str | None) -> str:
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return reverse("portal:search")


def client_ip(request) -> str:
    """The caller's address. Behind App Service the front end appends it to X-Forwarded-For, so the
    right-most entry is the one a client cannot forge."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        last = forwarded.split(",")[-1].strip()
        if last.startswith("["):  # [IPv6]:port
            return last[1:].split("]")[0]
        return last.rsplit(":", 1)[0] if last.count(":") == 1 else last
    return request.META.get("REMOTE_ADDR", "")


def _failure_key(request) -> str:
    return f"demo-login-failures:{client_ip(request)}"


@require_http_methods(["GET", "POST"])
def login(request):
    mode = settings.AUTH_MODE
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    configured = mode == "dev" or bool(settings.DEMO_PASSWORD)
    context = {"mode": mode, "next": next_url, "configured": configured, "error": "",
               "roles": [(r, ROLE_DESCRIPTIONS[r]) for r in ALL_ROLES], "selected_role": "User"}
    if request.user.is_authenticated and request.method == "GET":
        return redirect(_safe_next(request, next_url))
    if request.method == "GET":
        return render(request, "accounts/login.html", context)

    role = request.POST.get("role", "")
    context["selected_role"] = role if role in ALL_ROLES else "User"
    if not configured:
        context["error"] = "Sign-in is not configured: no demo password has been set for this environment."
        return render(request, "accounts/login.html", context, status=503)
    if role not in ALL_ROLES:
        context["error"] = "Choose a role: Admin or User."
        return render(request, "accounts/login.html", context, status=400)

    if mode == "password":
        key = _failure_key(request)
        failures = cache.get(key, 0)
        if failures >= settings.DEMO_PASSWORD_MAX_FAILURES:
            context["error"] = "Too many wrong passwords. Sign-in is blocked for 15 minutes."
            context["locked"] = True
            return render(request, "accounts/login.html", context, status=429)
        given = request.POST.get("password", "")
        if not hmac.compare_digest(given.encode(), settings.DEMO_PASSWORD.encode()):
            cache.set(key, failures + 1, settings.DEMO_PASSWORD_LOCKOUT_SECONDS)
            left = settings.DEMO_PASSWORD_MAX_FAILURES - failures - 1
            log.warning("Wrong demo password from %s (%s attempts left)", client_ip(request), left)
            context["error"] = "Wrong password." + (f" {left} attempt{'s' if left != 1 else ''} left before a 15-minute block."
                                                     if left <= 2 else "")
            return render(request, "accounts/login.html", context, status=403)
        cache.delete(key)

    request.session.cycle_key()
    user = User(role=role, signed_in_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    request.session["user"] = user.to_session()
    log.info("Signed in as %s from %s", role, client_ip(request))
    return redirect(_safe_next(request, next_url))


@require_POST
def logout(request):
    request.session.flush()
    return redirect("accounts:login")
