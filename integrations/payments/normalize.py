"""Normaliza payloads de webhook de gateway para o formato canônico do Hub."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from integrations.payments.inter_status import (
    extract_inter_cobranca,
    inter_artifacts,
    map_inter_situacao,
)


def normalize_gateway_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Aceita:
    - canônico Hub: tenant_slug, idempotency_key, gateway_ref, amount_cents, paid_at
    - Asaas-like: event + payment {id, value, externalReference, ...}
    - Inter Cobrança v3: cobranca/situacao/codigoSolicitacao (ou callback leve só com código)
    """
    if payload.get("gateway_ref") and payload.get("idempotency_key"):
        out = dict(payload)
        if "amount_cents" in out and out["amount_cents"] is not None:
            out["amount_cents"] = int(out["amount_cents"])
        return out

    payment = payload.get("payment")
    if isinstance(payment, dict) and payment.get("id"):
        return _normalize_asaas(payload, payment)

    inter = _normalize_inter(payload)
    if inter is not None:
        return inter

    raise ValueError("Formato de webhook de gateway não suportado")


def _normalize_asaas(payload: dict[str, Any], payment: dict[str, Any]) -> dict[str, Any]:
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
        "hub_status": "paid",
    }


def _looks_like_inter(payload: dict[str, Any]) -> bool:
    if str(payload.get("provider") or "").lower() == "inter":
        return True
    if payload.get("codigoSolicitacao"):
        return True
    cob = payload.get("cobranca")
    if isinstance(cob, dict) and (
        cob.get("codigoSolicitacao") or cob.get("situacao")
    ):
        return True
    return False


def _normalize_inter(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not _looks_like_inter(payload):
        return None

    arts = inter_artifacts(payload)
    cob = extract_inter_cobranca(payload)
    ref = (
        arts.get("codigo_solicitacao")
        or payload.get("codigoSolicitacao")
        or cob.get("codigoSolicitacao")
        or payload.get("gateway_ref")
        or ""
    )
    ref = str(ref).strip()
    if not ref:
        raise ValueError("Webhook Inter sem codigoSolicitacao")

    situacao = (arts.get("situacao") or payload.get("situacao") or "").strip().upper()
    hub_status = map_inter_situacao(situacao) if situacao else None
    amount = arts.get("received_cents")
    if amount is None:
        amount = arts.get("amount_cents")
    data_sit = arts.get("data_situacao") or ""
    paid_raw = data_sit or payload.get("paid_at") or ""
    paid_at = parse_datetime(str(paid_raw)) if paid_raw else None
    if paid_at is None:
        paid_at = timezone.now()

    needs_enrich = not situacao or (
        hub_status == "paid" and amount is None
    )
    event = situacao or str(payload.get("event") or "INTER_CALLBACK")
    idem = payload.get("idempotency_key") or f"{event}:{ref}:{data_sit}"

    out: dict[str, Any] = {
        "tenant_slug": payload.get("tenant_slug") or "",
        "idempotency_key": str(idem),
        "gateway_ref": ref,
        "paid_at": paid_at.isoformat(),
        "external_reference": str(
            arts.get("seu_numero")
            or payload.get("seuNumero")
            or payload.get("external_reference")
            or ""
        ),
        "event": event,
        "provider": "inter",
        "situacao": situacao,
        "needs_enrich": needs_enrich,
    }
    if hub_status:
        out["hub_status"] = hub_status
    if amount is not None:
        out["amount_cents"] = int(amount)
    return out
