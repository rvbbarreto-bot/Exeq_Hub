"""Normalização de notificações Mercado Pago → domínio Food."""

from __future__ import annotations

from typing import Any


def extract_payment_id(
    *,
    payload: dict[str, Any],
    query_params: dict[str, str] | None = None,
) -> str:
    query_params = query_params or {}
    data_id = (query_params.get("data.id") or query_params.get("id") or "").strip()
    if data_id:
        return data_id

    data = payload.get("data")
    if isinstance(data, dict):
        pid = data.get("id")
        if pid is not None:
            return str(pid).strip()
    if payload.get("id") is not None and payload.get("type") == "payment":
        return str(payload["id"]).strip()
    return ""


def extract_event_id(
    *,
    payload: dict[str, Any],
    x_request_id: str = "",
) -> str:
    req = (x_request_id or "").strip()
    if req:
        return req[:128]
    notif_id = payload.get("id")
    if notif_id is not None:
        return str(notif_id)[:128]
    action = str(payload.get("action") or "payment")
    data = payload.get("data") or {}
    pid = data.get("id") if isinstance(data, dict) else ""
    return f"{action}:{pid}"[:128]


def map_mp_status(status: str) -> str:
    """Retorna status FoodPayment: paid | failed | awaiting_payment | cancelled | expired."""
    raw = (status or "").lower().strip()
    if raw in {"approved", "accredited"}:
        return "paid"
    if raw in {"rejected", "refunded", "charged_back"}:
        return "failed"
    if raw in {"cancelled", "canceled"}:
        return "cancelled"
    if raw in {"expired"}:
        return "expired"
    return "awaiting_payment"


def payment_amount_cents(data: dict[str, Any]) -> int | None:
    amount = data.get("transaction_amount")
    if amount is None:
        return None
    try:
        return int(round(float(amount) * 100))
    except (TypeError, ValueError):
        return None
