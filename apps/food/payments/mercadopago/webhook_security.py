"""Validação de assinatura webhook Mercado Pago (Food)."""

from __future__ import annotations

import hashlib
import hmac
import re

from django.conf import settings

from apps.accounts.secrets import get_tenant_secret_plaintext


_SIGNATURE_RE = re.compile(
    r"ts=(?P<ts>[^,]+),v1=(?P<v1>[a-fA-F0-9]+)",
    re.IGNORECASE,
)


def get_webhook_secret(*, tenant) -> str:
    secret = get_tenant_secret_plaintext(
        tenant=tenant,
        provider="mercadopago",
        key_name="webhook_secret",
    )
    if not secret:
        secret = getattr(settings, "FOOD_MP_WEBHOOK_SECRET", "") or ""
    return (secret or "").strip()


def parse_x_signature(header: str) -> tuple[str, str]:
    match = _SIGNATURE_RE.search(header or "")
    if not match:
        return "", ""
    return match.group("ts"), match.group("v1")


def build_signature_manifest(*, data_id: str, request_id: str, ts: str) -> str:
    return f"id:{data_id};request-id:{request_id};ts:{ts};"


def verify_mercadopago_signature(
    *,
    secret: str,
    x_signature: str,
    x_request_id: str,
    data_id: str,
) -> bool:
    if not secret:
        return False
    ts, v1 = parse_x_signature(x_signature)
    if not ts or not v1 or not x_request_id or not data_id:
        return False
    manifest = build_signature_manifest(
        data_id=data_id,
        request_id=x_request_id,
        ts=ts,
    )
    expected = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, v1)
