"""Observabilidade fiscal iFood — logs estruturados + auditoria (B10 / EX-SEC-04)."""

from __future__ import annotations

import logging
import re
from typing import Any

from apps.food.models import FoodFiscalEvent, FoodOrder

FISCAL_LOGGER = logging.getLogger("exeq.food.fiscal")

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "authorization",
        "csc_token",
        "secret",
        "api_key",
        "api_token",
        "access_token",
        "refresh_token",
        "pix_copy_paste",
        "card_token",
        "pfx",
        "certificate",
        "signed_xml",
        "xml",
        "gateway_payload",
    }
)

_BEARER_RE = re.compile(r"Bearer\s+\S+", re.I)


def sanitize_log_extra(extra: dict[str, Any] | None) -> dict[str, Any]:
    if not extra:
        return {}
    out: dict[str, Any] = {}
    for key, value in extra.items():
        lk = str(key).lower()
        if lk in _SENSITIVE_KEYS:
            out[key] = "[redacted]"
            continue
        if isinstance(value, str):
            if lk in {"document", "cpf", "cnpj", "customer_document"} and len(value) > 4:
                out[key] = value[:3] + "***"
            elif "token" in lk or "secret" in lk or "password" in lk:
                out[key] = "[redacted]"
            else:
                out[key] = _BEARER_RE.sub("Bearer [redacted]", value)
        elif isinstance(value, dict):
            out[key] = sanitize_log_extra(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = str(value)[:200]
    return out


def log_fiscal_event(
    action: str,
    *,
    tenant_id,
    order_id=None,
    attempt: int | None = None,
    actor: str | None = None,
    level: int = logging.INFO,
    **extra: Any,
) -> None:
    safe = sanitize_log_extra(extra)
    FISCAL_LOGGER.log(
        level,
        "food.fiscal.%s tenant=%s order=%s attempt=%s actor=%s",
        action,
        tenant_id,
        order_id or "-",
        attempt if attempt is not None else "-",
        actor or "-",
        extra={"fiscal": {"action": action, **safe}},
    )


def audit_food_fiscal(
    *,
    tenant,
    order: FoodOrder,
    action: str,
    actor: str,
    from_status: str = "",
    to_status: str = "",
    metadata: dict[str, Any] | None = None,
) -> FoodFiscalEvent:
    attempt = int(order.fiscal_emit_attempt or 0)
    safe_meta = sanitize_log_extra(metadata or {})
    ev = FoodFiscalEvent.objects.create(
        tenant=tenant,
        order=order,
        action=action,
        actor=(actor or "system")[:64],
        from_status=(from_status or "")[:16],
        to_status=(to_status or order.fiscal_status or "")[:16],
        attempt=attempt,
        metadata=safe_meta or None,
    )
    log_fiscal_event(
        action,
        tenant_id=tenant.id,
        order_id=order.id,
        attempt=attempt,
        actor=actor,
        event_id=str(ev.id),
        from_status=from_status,
        to_status=ev.to_status,
        **(safe_meta or {}),
    )
    return ev


def log_fiscal_batch_summary(
    *,
    tenant,
    batch_id: str,
    summary: dict[str, Any],
    actor: str,
) -> None:
    log_fiscal_event(
        "batch_done",
        tenant_id=tenant.id,
        actor=actor,
        batch_id=batch_id[:36],
        total=summary.get("total"),
        authorized=summary.get("authorized"),
        failed=summary.get("failed"),
        skipped=summary.get("skipped"),
        rejected_cross_tenant=summary.get("rejected_cross_tenant"),
    )


def serialize_fiscal_event(ev: FoodFiscalEvent) -> dict[str, Any]:
    return {
        "id": str(ev.id),
        "action": ev.action,
        "actor": ev.actor,
        "from_status": ev.from_status,
        "to_status": ev.to_status,
        "attempt": ev.attempt,
        "metadata": ev.metadata or {},
        "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
    }
