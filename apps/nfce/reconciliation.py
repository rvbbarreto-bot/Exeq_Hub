"""RF-46 NFC-e — reconcilia polling/submitting órfãos."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.nfce.models import NfceInvoice, NfceInvoiceEvent

logger = logging.getLogger(__name__)


def reconcile_stale_seconds() -> int:
    return max(
        30,
        int(
            getattr(settings, "NFCE_RECONCILE_STALE_SECONDS", None)
            or getattr(settings, "NFE_RECONCILE_STALE_SECONDS", 120)
            or 120
        ),
    )


def _record_event(invoice: NfceInvoice, *, from_status: str, to_status: str, metadata: dict) -> None:
    NfceInvoiceEvent.objects.create(
        tenant_id=invoice.tenant_id,
        invoice=invoice,
        from_status=from_status,
        to_status=to_status,
        actor="reconcile",
        metadata=metadata,
    )


def invoices_stale_polling(*, limit: int = 50):
    cutoff = timezone.now() - timedelta(seconds=reconcile_stale_seconds())
    return list(
        NfceInvoice.objects.filter(status=NfceInvoice.Status.POLLING, updated_at__lte=cutoff)
        .order_by("updated_at")[: max(1, int(limit or 50))]
    )


def invoices_stale_submitting(*, limit: int = 50):
    cutoff = timezone.now() - timedelta(seconds=reconcile_stale_seconds())
    return list(
        NfceInvoice.objects.filter(status=NfceInvoice.Status.SUBMITTING, updated_at__lte=cutoff)
        .order_by("updated_at")[: max(1, int(limit or 50))]
    )


@transaction.atomic
def _recover_submitting(invoice: NfceInvoice) -> str:
    inv = NfceInvoice.objects.select_for_update().filter(pk=invoice.pk).first()
    if inv is None or inv.status != NfceInvoice.Status.SUBMITTING:
        return "skip"
    prev = inv.status
    key = "".join(ch for ch in str(inv.access_key or "") if ch.isdigit())
    if key:
        inv.status = NfceInvoice.Status.POLLING
        inv.number_consumed = True
        inv.save(update_fields=["status", "number_consumed", "updated_at"])
        _record_event(
            inv,
            from_status=prev,
            to_status=inv.status,
            metadata={"reason": "reconcile_submit_to_poll", "access_key": key[:10]},
        )
        return "polling"
    inv.status = NfceInvoice.Status.FAILED
    inv.rejection_code = "SUBMIT_ORPHAN"
    inv.rejection_message = "Emissão NFC-e interrompida sem chave/recibo"
    if inv.number is not None:
        inv.number_consumed = True
    inv.save(
        update_fields=[
            "status",
            "rejection_code",
            "rejection_message",
            "number_consumed",
            "updated_at",
        ]
    )
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        metadata={"reason": "submit_orphan"},
    )
    logger.warning("nfce.submit_orphan invoice=%s tenant=%s", inv.id, inv.tenant_id)
    return "failed"


def reconcile_stale_nfce_batch(*, limit: int = 50) -> dict[str, int]:
    from apps.nfce.polling import schedule_nfce_poll

    stats = {
        "polling_scheduled": 0,
        "submit_to_poll": 0,
        "submit_orphan": 0,
        "skipped": 0,
    }
    half = max(1, limit // 2)

    for inv in invoices_stale_polling(limit=half):
        try:
            schedule_nfce_poll(inv)
            stats["polling_scheduled"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("nfce.reconcile_poll_schedule_failed invoice=%s", inv.id)
            stats["skipped"] += 1

    for inv in invoices_stale_submitting(limit=half):
        try:
            outcome = _recover_submitting(inv)
            if outcome == "polling":
                inv.refresh_from_db()
                schedule_nfce_poll(inv)
                stats["submit_to_poll"] += 1
            elif outcome == "failed":
                stats["submit_orphan"] += 1
            else:
                stats["skipped"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("nfce.reconcile_submit_failed invoice=%s", inv.id)
            stats["skipped"] += 1

    return stats
