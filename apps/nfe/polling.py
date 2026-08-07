"""Reconciliação NF-e em `polling` (I5) — consulta recibo/chave, teto → failed."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.nfe.models import NfeInvoice, NfeInvoiceEvent
from integrations.sefaz_nfe import get_nfe_provider

logger = logging.getLogger(__name__)


def _record_event(
    invoice: NfeInvoice,
    *,
    from_status: str,
    to_status: str,
    actor: str = "worker",
    metadata: dict | None = None,
) -> None:
    NfeInvoiceEvent.objects.create(
        tenant_id=invoice.tenant_id,
        invoice=invoice,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        metadata=metadata,
    )


def _sefaz_meta(snapshot: dict | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    sefaz = snapshot.get("sefaz")
    return dict(sefaz) if isinstance(sefaz, dict) else {}


def _write_sefaz_meta(invoice: NfeInvoice, **fields: Any) -> None:
    snap = dict(invoice.fiscal_snapshot or {})
    sefaz = _sefaz_meta(snap)
    sefaz.update({k: v for k, v in fields.items() if v is not None})
    snap["sefaz"] = sefaz
    invoice.fiscal_snapshot = snap


def max_poll_attempts() -> int:
    return max(1, int(getattr(settings, "NFE_POLL_MAX_ATTEMPTS", 12) or 12))


def poll_countdown_seconds() -> int:
    return max(1, int(getattr(settings, "NFE_POLL_COUNTDOWN", 15) or 15))


@transaction.atomic
def poll_nfe_invoice(invoice: NfeInvoice, *, actor: str = "worker") -> NfeInvoice:
    """
    Uma rodada de consulta SEFAZ enquanto `polling`.

    - polling → authorized | rejected | failed | polling
    - não reserva/libera número (D-06: sem reentrada)
    - teto de tentativas → failed + log de alerta (FSM-05)
    """
    inv = NfeInvoice.objects.select_for_update().get(pk=invoice.pk)
    if inv.status != NfeInvoice.Status.POLLING:
        return inv

    sefaz = _sefaz_meta(inv.fiscal_snapshot)
    attempts = int(sefaz.get("poll_attempts") or 0) + 1
    n_rec = str(sefaz.get("n_rec") or "").strip()
    max_att = max_poll_attempts()

    if attempts > max_att:
        prev = inv.status
        inv.status = NfeInvoice.Status.FAILED
        inv.rejection_code = "POLL_EXHAUSTED"
        inv.rejection_message = f"Poll esgotado após {max_att} tentativas (FSM-05)"
        inv.version += 1
        # número já consumido em polling — não reentra na série
        inv.number_consumed = True
        _write_sefaz_meta(inv, poll_attempts=attempts)
        inv.save()
        _record_event(
            inv,
            from_status=prev,
            to_status=inv.status,
            actor=actor,
            metadata={
                "reason": "poll_exhausted",
                "poll_attempts": attempts,
                "max_attempts": max_att,
            },
        )
        logger.warning(
            "nfe.poll_exhausted invoice=%s tenant=%s attempts=%s (alerta ops FSM-05)",
            inv.id,
            inv.tenant_id,
            attempts,
        )
        from apps.nfe.outbox import publish_poll_exhausted

        publish_poll_exhausted(
            inv, poll_attempts=attempts, max_attempts=max_att
        )
        return inv

    provider = get_nfe_provider()
    cnpj = ""
    if isinstance(inv.fiscal_snapshot, dict):
        emit = inv.fiscal_snapshot.get("emitente") or {}
        cnpj = "".join(ch for ch in str(emit.get("cnpj") or "") if ch.isdigit())
    if not cnpj and inv.provider_id:
        cnpj = "".join(ch for ch in str(getattr(inv.provider, "document", "") or "") if ch.isdigit())

    uf = getattr(settings, "NFE_PIVOT_UF", "SP")
    if isinstance(inv.fiscal_snapshot, dict):
        addr = (inv.fiscal_snapshot.get("emitente") or {}).get("address") or {}
        if addr.get("uf"):
            uf = str(addr["uf"]).upper()

    result = provider.consultar(
        access_key=inv.access_key or "",
        receipt=n_rec,
        tp_amb=inv.tp_amb or "2",
        context={
            "tenant": inv.tenant,
            "invoice_id": str(inv.id),
            "cnpj": cnpj,
            "uf": uf,
        },
    )

    raw_meta = result.raw if isinstance(result.raw, dict) else {}
    # Persist nRec se a consulta devolver outro (raro) e contador
    new_rec = str(raw_meta.get("nRec") or n_rec or "").strip()
    _write_sefaz_meta(inv, poll_attempts=attempts, n_rec=new_rec or n_rec)

    prev = inv.status
    if result.status == "authorized":
        inv.status = NfeInvoice.Status.AUTHORIZED
        inv.access_key = result.access_key or inv.access_key
        inv.protocol = result.protocol or inv.protocol
        inv.number_consumed = True
        inv.rejection_code = ""
        inv.rejection_message = ""
    elif result.status == "rejected":
        inv.status = NfeInvoice.Status.REJECTED
        inv.access_key = result.access_key or inv.access_key
        inv.rejection_code = result.rejection_code
        inv.rejection_message = result.rejection_message
        inv.number_consumed = True
    elif result.status == "polling":
        inv.status = NfeInvoice.Status.POLLING
        inv.access_key = result.access_key or inv.access_key
        inv.rejection_code = result.rejection_code or inv.rejection_code
        inv.rejection_message = result.rejection_message or inv.rejection_message
        inv.number_consumed = True
    else:
        # falha transitória de transport: permanece polling para nova tentativa;
        # se CERT/REF definitivo o caller ainda conta no teto
        permanent = (result.rejection_code or "") in {"CERT", "REF"}
        if permanent:
            inv.status = NfeInvoice.Status.FAILED
            inv.rejection_code = result.rejection_code or "failed"
            inv.rejection_message = result.rejection_message or "falha na consulta SEFAZ"
            inv.number_consumed = True
        else:
            inv.status = NfeInvoice.Status.POLLING
            inv.rejection_code = result.rejection_code or inv.rejection_code
            inv.rejection_message = result.rejection_message or inv.rejection_message
            inv.number_consumed = True

    inv.version += 1
    inv.save()
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        actor=actor,
        metadata={
            "provider": provider.kind,
            "action": "consultar",
            "poll_attempts": attempts,
            "raw": raw_meta,
        },
    )

    if inv.status == NfeInvoice.Status.AUTHORIZED:
        from apps.nfe.artifacts import ensure_authorized_artifacts

        signed = getattr(result, "signed_xml", None)
        ensure_authorized_artifacts(
            inv,
            xml_bytes=signed if isinstance(signed, (bytes, bytearray)) else None,
            provider_raw=raw_meta,
        )
        from apps.nfe.outbox import publish_after_terminal_status

        publish_after_terminal_status(inv)
    elif inv.status == NfeInvoice.Status.REJECTED:
        from apps.nfe.outbox import publish_after_terminal_status

        publish_after_terminal_status(inv)
    return inv


def schedule_nfe_poll(invoice: NfeInvoice) -> None:
    """Agenda reconciliação Celery (ou roda síncrono em lab eager)."""
    if invoice.status != NfeInvoice.Status.POLLING:
        return

    sync = bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)) or bool(
        getattr(settings, "NFE_SYNC_POLL", False)
    )
    if sync:
        poll_nfe_invoice(invoice)
        return

    from apps.nfe.tasks import poll_nfe_invoice_task

    poll_nfe_invoice_task.apply_async(
        args=[str(invoice.tenant_id), str(invoice.id)],
        countdown=poll_countdown_seconds(),
    )
