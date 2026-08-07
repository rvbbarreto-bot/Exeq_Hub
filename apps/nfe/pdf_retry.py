"""RF-64 EX-PDF — retry DANFE para authorized com pdf_pending."""

from __future__ import annotations

import logging

from apps.nfe.artifacts import ensure_danfe_pdf, has_danfe_pdf
from apps.nfe.models import NfeInvoice

logger = logging.getLogger(__name__)


def invoices_with_pdf_pending(*, limit: int = 50):
    """NF-e authorized com flag pdf_pending (JSONField key transform)."""
    return list(
        NfeInvoice.objects.filter(
            status=NfeInvoice.Status.AUTHORIZED,
            last_validation__pdf_pending=True,
        ).order_by("updated_at")[: max(1, int(limit or 50))]
    )


def retry_pending_danfe_for_invoice(invoice: NfeInvoice) -> bool:
    """Tenta gerar DANFE. True se PDF ok após tentativa. Não altera authorized."""
    if invoice.status != NfeInvoice.Status.AUTHORIZED:
        return False
    if has_danfe_pdf(invoice):
        flags = dict(invoice.last_validation or {})
        if flags.pop("pdf_pending", None) is not None:
            invoice.last_validation = flags
            invoice.save(update_fields=["last_validation", "updated_at"])
        return True
    art = ensure_danfe_pdf(invoice, cancelled=False)
    ok = art is not None or has_danfe_pdf(invoice)
    if ok:
        logger.info("nfe.pdf_retry_ok invoice=%s", invoice.id)
    else:
        logger.warning("nfe.pdf_retry_pending invoice=%s", invoice.id)
    return ok


def retry_pending_danfe_batch(*, limit: int = 50) -> dict[str, int]:
    """Processa lote de pdf_pending. Retorna contadores."""
    rows = invoices_with_pdf_pending(limit=limit)
    ok = 0
    failed = 0
    for inv in rows:
        try:
            if retry_pending_danfe_for_invoice(inv):
                ok += 1
            else:
                failed += 1
        except Exception:  # noqa: BLE001
            logger.exception("nfe.pdf_retry_error invoice=%s", inv.id)
            failed += 1
    return {"scanned": len(rows), "ok": ok, "failed": failed}
