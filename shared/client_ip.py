"""Resolução de IP do cliente e allowlists (SEC-P1-05 / webhooks)."""

from __future__ import annotations

from django.conf import settings


def client_ip(request, *, trust_x_forwarded_for: bool = False) -> str:
    if trust_x_forwarded_for:
        forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return (request.META.get("REMOTE_ADDR") or "").strip()


def ip_allowed(request, *, allowed: list[str] | None, trust_x_forwarded_for: bool) -> bool:
    """True se allowlist vazia (lab) ou IP está na lista."""
    if not allowed:
        return True
    ip = client_ip(request, trust_x_forwarded_for=trust_x_forwarded_for)
    return bool(ip) and ip in allowed
