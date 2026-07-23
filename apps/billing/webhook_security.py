"""Utilitários de rede para webhook gateway (IP allowlist)."""

from __future__ import annotations

from django.conf import settings


def client_ip(request) -> str:
    """IP do peer. Só confia em X-Forwarded-For se WEBHOOK_TRUST_X_FORWARDED_FOR."""
    if getattr(settings, "WEBHOOK_TRUST_X_FORWARDED_FOR", False):
        forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return (request.META.get("REMOTE_ADDR") or "").strip()


def webhook_ip_allowed(request) -> bool:
    """
    True se allowlist vazia (lab) ou IP do cliente está na lista.
    Em produção configure WEBHOOK_ALLOWED_IPS com o IP do proxy assinador.
    """
    allowed = getattr(settings, "WEBHOOK_ALLOWED_IPS", None) or []
    if not allowed:
        return True
    ip = client_ip(request)
    return bool(ip) and ip in allowed
