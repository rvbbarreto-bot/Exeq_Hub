"""Celery — poll NFC-e em status polling."""

from __future__ import annotations

from celery import shared_task

from apps.accounts.models import Tenant
from apps.nfce.models import NfceInvoice
from apps.nfce.polling import max_poll_attempts, poll_countdown_seconds, poll_nfce_invoice


@shared_task(
    bind=True,
    max_retries=max_poll_attempts(),
    default_retry_delay=poll_countdown_seconds(),
    name="nfce.poll_nfce_invoice",
)
def poll_nfce_invoice_task(self, tenant_id: str, invoice_id: str) -> str:
    tenant = Tenant.objects.filter(id=tenant_id).first()
    if tenant is None:
        return "tenant_missing"
    inv = NfceInvoice.objects.filter(tenant=tenant, id=invoice_id).first()
    if inv is None:
        return "invoice_missing"
    if inv.status != NfceInvoice.Status.POLLING:
        return inv.status
    poll_nfce_invoice(inv, actor="worker")
    inv.refresh_from_db()
    if inv.status == NfceInvoice.Status.POLLING:
        raise self.retry()
    return inv.status


@shared_task(name="nfce.reconcile_stale")
def reconcile_stale_nfce_task(limit: int = 50) -> dict:
    from apps.nfce.reconciliation import reconcile_stale_nfce_batch

    return reconcile_stale_nfce_batch(limit=limit)
