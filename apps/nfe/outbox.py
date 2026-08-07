"""Outbox de domínio NF-e (RF-70) — mesma transação do fato fiscal."""

from __future__ import annotations

from typing import Any

from apps.nfe.models import NfeInvoice
from apps.ops.services import enqueue_outbox

SCHEMA_VERSION = 1

EVENT_AUTHORIZED = "nfe.authorized"
EVENT_REJECTED = "nfe.rejected"
EVENT_CANCELLED = "nfe.cancelled"
EVENT_POLL_EXHAUSTED = "nfe.poll_exhausted"


def _payload(invoice: NfeInvoice, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "nfe_invoice_id": str(invoice.id),
        "status": invoice.status,
        "series": invoice.series,
        "number": invoice.number,
        "access_key": invoice.access_key or "",
        "protocol": invoice.protocol or "",
        "tp_amb": invoice.tp_amb or "",
        "rejection_code": invoice.rejection_code or "",
        "total_cents": invoice.total_cents,
        "provider_id": str(invoice.provider_id) if invoice.provider_id else "",
        "customer_id": str(invoice.customer_id) if invoice.customer_id else "",
    }
    if extra:
        body.update(extra)
    return body


def publish_nfe_lifecycle_event(
    invoice: NfeInvoice,
    *,
    event_type: str,
    extra: dict[str, Any] | None = None,
):
    """Enfileira outbox (dispatch on_commit). aggregate=nfe_invoice."""
    return enqueue_outbox(
        tenant=invoice.tenant,
        event_type=event_type,
        aggregate_type="nfe_invoice",
        aggregate_id=invoice.id,
        payload=_payload(invoice, extra=extra),
        correlation_id=invoice.correlation_id,
    )


def publish_after_terminal_status(invoice: NfeInvoice) -> None:
    """Dispara evento se status for authorized/rejected/cancelled."""
    if invoice.status == NfeInvoice.Status.AUTHORIZED:
        publish_nfe_lifecycle_event(invoice, event_type=EVENT_AUTHORIZED)
    elif invoice.status == NfeInvoice.Status.REJECTED:
        publish_nfe_lifecycle_event(invoice, event_type=EVENT_REJECTED)
    elif invoice.status == NfeInvoice.Status.CANCELLED:
        publish_nfe_lifecycle_event(invoice, event_type=EVENT_CANCELLED)


def publish_poll_exhausted(invoice: NfeInvoice, *, poll_attempts: int, max_attempts: int) -> None:
    """RF-92 — alerta outbox quando poll esgota (authorize não acontece)."""
    publish_nfe_lifecycle_event(
        invoice,
        event_type=EVENT_POLL_EXHAUSTED,
        extra={
            "poll_attempts": poll_attempts,
            "max_attempts": max_attempts,
            "reason": "poll_exhausted",
        },
    )
