"""Celery tasks NF-e (I5 poll · RF-64 DANFE · RF-46 reconciliação)."""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction

from apps.nfe.models import NfeInvoice
from apps.nfe.polling import max_poll_attempts, poll_countdown_seconds, poll_nfe_invoice
from shared.rls import tenant_rls

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="nfe.poll_nfe_invoice",
    max_retries=24,
    default_retry_delay=15,
)
def poll_nfe_invoice_task(self, tenant_id: str, invoice_id: str) -> str:
    """Consulta recibo/chave enquanto status=polling; reagenda até saída ou teto."""
    with tenant_rls(tenant_id):
        with transaction.atomic():
            inv = (
                NfeInvoice.objects.select_for_update()
                .filter(tenant_id=tenant_id, id=invoice_id)
                .first()
            )
            if inv is None:
                return str(invoice_id)
            if inv.status != NfeInvoice.Status.POLLING:
                return str(invoice_id)
            poll_nfe_invoice(inv, actor="worker")
            inv.refresh_from_db()
            if inv.status != NfeInvoice.Status.POLLING:
                return str(invoice_id)

    if self.request.retries >= max_poll_attempts():
        logger.warning(
            "nfe.poll_task_retries_cap tenant=%s invoice=%s retries=%s",
            tenant_id,
            invoice_id,
            self.request.retries,
        )
        return str(invoice_id)

    countdown = poll_countdown_seconds()
    backoff = min(countdown * (2 ** min(self.request.retries, 4)), 300)
    raise self.retry(countdown=backoff)


@shared_task(name="nfe.retry_pending_danfe")
def retry_pending_danfe_task(limit: int = 50) -> dict:
    """RF-64 — reprocessa authorized com pdf_pending (beat)."""
    from apps.nfe.pdf_retry import retry_pending_danfe_batch

    result = retry_pending_danfe_batch(limit=limit)
    logger.info("nfe.retry_pending_danfe %s", result)
    return result


@shared_task(name="nfe.reconcile_stale")
def reconcile_stale_nfe_task(limit: int = 50) -> dict:
    """RF-46 — reengata polling órfão e submitting travado (beat)."""
    from apps.nfe.reconciliation import reconcile_stale_nfe_batch

    result = reconcile_stale_nfe_batch(limit=limit)
    logger.info("nfe.reconcile_stale %s", result)
    return result
