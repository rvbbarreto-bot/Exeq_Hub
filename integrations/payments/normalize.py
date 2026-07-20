"""Normaliza payloads de webhook de gateway para o formato canônico do Hub."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def normalize_gateway_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Aceita:
    - canônico Hub: tenant_slug, idempotency_key, gateway_ref, amount_cents, paid_at
    - Asaas-like: event + payment {id, value, externalReference, ...}
    """
    if payload.get("gateway_ref") and payload.get("idempotency_key"):
        out = dict(payload)
        if "amount_cents" in out:
            out["amount_cents"] = int(out["amount_cents"])
        return out

    payment = payload.get("payment")
    if isinstance(payment, dict) and payment.get("id"):
        value = payment.get("value")
        if value is None and payment.get("netValue") is not None:
            value = payment.get("netValue")
        amount_cents = int(round(float(value or 0) * 100))
        paid_raw = (
            payment.get("confirmedDate")
            or payment.get("paymentDate")
            or payment.get("clientPaymentDate")
            or ""
        )
        paid_at = parse_datetime(str(paid_raw)) if paid_raw else None
        event = str(payload.get("event") or "PAYMENT")
        return {
            "tenant_slug": payload.get("tenant_slug") or "",
            "idempotency_key": str(
                payload.get("idempotency_key")
                or payload.get("id")
                or f"{event}:{payment['id']}"
            ),
            "gateway_ref": str(payment["id"]),
            "amount_cents": amount_cents,
            "paid_at": (paid_at or timezone.now()).isoformat(),
            "external_reference": str(payment.get("externalReference") or ""),
            "event": event,
            "provider": "asaas",
        }

    return dict(payload)
