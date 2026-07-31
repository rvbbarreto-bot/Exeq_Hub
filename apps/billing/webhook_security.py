"""Utilitários de rede para webhook gateway (IP allowlist)."""

from __future__ import annotations

from django.conf import settings

from shared.client_ip import client_ip as resolve_client_ip
from shared.client_ip import ip_allowed


def client_ip(request) -> str:
    """IP do peer. Só confia em X-Forwarded-For se WEBHOOK_TRUST_X_FORWARDED_FOR."""
    return resolve_client_ip(
        request,
        trust_x_forwarded_for=getattr(settings, "WEBHOOK_TRUST_X_FORWARDED_FOR", False),
    )


def webhook_ip_allowed(request) -> bool:
    """
    True se allowlist vazia (lab) ou IP do cliente está na lista.
    Em produção configure WEBHOOK_ALLOWED_IPS com o IP do proxy assinador.
    """
    return ip_allowed(
        request,
        allowed=getattr(settings, "WEBHOOK_ALLOWED_IPS", None) or [],
        trust_x_forwarded_for=getattr(settings, "WEBHOOK_TRUST_X_FORWARDED_FOR", False),
    )
