"""RF-46 — reconciliação NF-e: reengata polling órfão / submitting / cancel_requested."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.nfe.models import NfeInvoice, NfeInvoiceEvent

logger = logging.getLogger(__name__)


def reconcile_stale_seconds() -> int:
    return max(30, int(getattr(settings, "NFE_RECONCILE_STALE_SECONDS", 120) or 120))


def _record_event(invoice: NfeInvoice, *, from_status: str, to_status: str, metadata: dict) -> None:
    NfeInvoiceEvent.objects.create(
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
        NfeInvoice.objects.filter(status=NfeInvoice.Status.POLLING, updated_at__lte=cutoff)
        .order_by("updated_at")[: max(1, int(limit or 50))]
    )


def invoices_stale_submitting(*, limit: int = 50):
    cutoff = timezone.now() - timedelta(seconds=reconcile_stale_seconds())
    return list(
        NfeInvoice.objects.filter(status=NfeInvoice.Status.SUBMITTING, updated_at__lte=cutoff)
        .order_by("updated_at")[: max(1, int(limit or 50))]
    )


def invoices_stale_cancel_requested(*, limit: int = 50):
    cutoff = timezone.now() - timedelta(seconds=reconcile_stale_seconds())
    return list(
        NfeInvoice.objects.filter(
            status=NfeInvoice.Status.CANCEL_REQUESTED, updated_at__lte=cutoff
        )
        .order_by("updated_at")[: max(1, int(limit or 50))]
    )


@transaction.atomic
def _recover_submitting(invoice: NfeInvoice) -> str:
    """
    Retorno: 'polling' | 'failed' | 'skip'.
    Com access_key → polling (consulta SEFAZ).
    Sem key → failed (POST não concluiu ou sem identificador).
    """
    inv = NfeInvoice.objects.select_for_update().filter(pk=invoice.pk).first()
    if inv is None or inv.status != NfeInvoice.Status.SUBMITTING:
        return "skip"
    prev = inv.status
    key = "".join(ch for ch in str(inv.access_key or "") if ch.isdigit())
    if key:
        inv.status = NfeInvoice.Status.POLLING
        inv.number_consumed = True
        inv.version += 1
        inv.save(
            update_fields=[
                "status",
                "number_consumed",
                "version",
                "updated_at",
            ]
        )
        _record_event(
            inv,
            from_status=prev,
            to_status=inv.status,
            metadata={"reason": "reconcile_submit_to_poll", "access_key": key[:10]},
        )
        return "polling"
    inv.status = NfeInvoice.Status.FAILED
    inv.rejection_code = "SUBMIT_ORPHAN"
    inv.rejection_message = "Emissão interrompida sem chave/recibo (reconciliação RF-46)"
    if inv.number is not None:
        inv.number_consumed = True
    inv.version += 1
    inv.save(
        update_fields=[
            "status",
            "rejection_code",
            "rejection_message",
            "number_consumed",
            "version",
            "updated_at",
        ]
    )
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        metadata={"reason": "submit_orphan"},
    )
    logger.warning(
        "nfe.submit_orphan invoice=%s tenant=%s number=%s",
        inv.id,
        inv.tenant_id,
        inv.number,
    )
    return "failed"


@transaction.atomic
def _recover_cancel_requested(invoice: NfeInvoice) -> str:
    """
    Cancel travado → volta authorized (EX-FIS-04) para reenvio seguro do 110111.
    Não assume cancelled na SEFAZ sem consulta de evento (ops/manual se dúvida).
    """
    inv = NfeInvoice.objects.select_for_update().filter(pk=invoice.pk).first()
    if inv is None or inv.status != NfeInvoice.Status.CANCEL_REQUESTED:
        return "skip"
    prev = inv.status
    inv.status = NfeInvoice.Status.AUTHORIZED
    inv.rejection_code = "CANCEL_ORPHAN"
    inv.rejection_message = (
        "Cancelamento interrompido (reconciliação) — reenviar cancel se necessário"
    )
    inv.version += 1
    inv.save(
        update_fields=[
            "status",
            "rejection_code",
            "rejection_message",
            "version",
            "updated_at",
        ]
    )
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        metadata={"reason": "cancel_orphan_restore_authorized"},
    )
    logger.warning(
        "nfe.cancel_orphan invoice=%s tenant=%s key=%s",
        inv.id,
        inv.tenant_id,
        (inv.access_key or "")[:10],
    )
    return "authorized"


def reconcile_stale_nfe_batch(*, limit: int = 50) -> dict[str, int]:
    """
    - polling stale → reagenda `schedule_nfe_poll`
    - submitting stale + chave → polling + agenda
    - submitting stale sem chave → failed SUBMIT_ORPHAN
    - cancel_requested stale → authorized CANCEL_ORPHAN
    """
    from apps.nfe.polling import schedule_nfe_poll

    stats = {
        "polling_scheduled": 0,
        "submit_to_poll": 0,
        "submit_orphan": 0,
        "cancel_restored": 0,
        "skipped": 0,
    }
    third = max(1, limit // 3)

    for inv in invoices_stale_polling(limit=third):
        try:
            schedule_nfe_poll(inv)
            stats["polling_scheduled"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("nfe.reconcile_poll_schedule_failed invoice=%s", inv.id)
            stats["skipped"] += 1

    for inv in invoices_stale_submitting(limit=third):
        try:
            outcome = _recover_submitting(inv)
            if outcome == "polling":
                inv.refresh_from_db()
                schedule_nfe_poll(inv)
                stats["submit_to_poll"] += 1
            elif outcome == "failed":
                stats["submit_orphan"] += 1
            else:
                stats["skipped"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("nfe.reconcile_submit_failed invoice=%s", inv.id)
            stats["skipped"] += 1

    for inv in invoices_stale_cancel_requested(limit=third):
        try:
            outcome = _recover_cancel_requested(inv)
            if outcome == "authorized":
                stats["cancel_restored"] += 1
            else:
                stats["skipped"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("nfe.reconcile_cancel_failed invoice=%s", inv.id)
            stats["skipped"] += 1

    logger.info("nfe.reconcile_batch %s", stats)
    return stats
