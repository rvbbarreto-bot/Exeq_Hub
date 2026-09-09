"""Detecta cancelamento em payloads marketplace (iFood/aiqfome)."""

from __future__ import annotations

from typing import Any

_CANCELLED_VALUES = frozenset(
    {
        "cancelled",
        "canceled",
        "cancelado",
        "cancelled_by_merchant",
        "cancelled_by_customer",
        "cancelled_by_ifood",
        "cancelled_by_platform",
        "declined",
        "rejected",
    }
)


def marketplace_payload_cancelled(raw: dict[str, Any]) -> bool:
    if raw.get("cancelled") is True or raw.get("canceled") is True:
        return True
    for key in ("status", "orderStatus", "order_status", "state", "logistic_status"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip().lower() in _CANCELLED_VALUES:
            return True
    return False
