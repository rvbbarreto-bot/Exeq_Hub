"""CSRF — recuperação amigável no login Hub."""

from __future__ import annotations

from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.csrf import csrf_failure as django_csrf_failure


def hub_csrf_failure(request, reason=""):
    login_path = reverse("hub-v4-login").rstrip("/")
    logout_path = reverse("hub-v4-logout").rstrip("/")
    path = (request.path or "").rstrip("/")
    if request.method == "POST" and path == logout_path:
        from apps.hub_v4.auth import clear_hub_session

        clear_hub_session(request)
        request.session.flush()
        return HttpResponseRedirect(f"{reverse('hub-v4-login')}?logged_out=1")
    if request.method == "POST" and path == login_path:
        return HttpResponseRedirect(f"{reverse('hub-v4-login')}?err=csrf")
    return django_csrf_failure(request, reason=reason)
