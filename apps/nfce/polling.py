"""Reconciliação NFC-e em `polling` — consulta recibo/chave SEFAZ."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.nfce.models import NfceInvoice, NfceInvoiceEvent
from integrations.sefaz_nfe import get_nfce_provider

logger = logging.getLogger(__name__)


def _record_event(
    invoice: NfceInvoice,
    *,
    from_status: str,
    to_status: str,
    actor: str = "worker",
    metadata: dict | None = None,
) -> None:
    NfceInvoiceEvent.objects.create(
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


def _write_sefaz_meta(invoice: NfceInvoice, **fields: Any) -> None:
    snap = dict(invoice.fiscal_snapshot or {})
    sefaz = _sefaz_meta(snap)
    sefaz.update({k: v for k, v in fields.items() if v is not None})
    snap["sefaz"] = sefaz
    invoice.fiscal_snapshot = snap


def max_poll_attempts() -> int:
    return max(
        1,
        int(
            getattr(settings, "NFCE_POLL_MAX_ATTEMPTS", None)
            or getattr(settings, "NFE_POLL_MAX_ATTEMPTS", 12)
            or 12
        ),
    )


def poll_countdown_seconds() -> int:
    return max(
        1,
        int(
            getattr(settings, "NFCE_POLL_COUNTDOWN", None)
            or getattr(settings, "NFE_POLL_COUNTDOWN", 15)
            or 15
        ),
    )


@transaction.atomic
def poll_nfce_invoice(invoice: NfceInvoice, *, actor: str = "worker") -> NfceInvoice:
    inv = NfceInvoice.objects.select_for_update().get(pk=invoice.pk)
    if inv.status != NfceInvoice.Status.POLLING:
        return inv

    sefaz = _sefaz_meta(inv.fiscal_snapshot)
    attempts = int(sefaz.get("poll_attempts") or 0) + 1
    n_rec = str(sefaz.get("n_rec") or "").strip()
    max_att = max_poll_attempts()

    if attempts > max_att:
        prev = inv.status
        inv.status = NfceInvoice.Status.FAILED
        inv.rejection_code = "POLL_EXHAUSTED"
        inv.rejection_message = f"Poll esgotado após {max_att} tentativas"
        inv.number_consumed = True
        _write_sefaz_meta(inv, poll_attempts=attempts)
        inv.save()
        _record_event(
            inv,
            from_status=prev,
            to_status=inv.status,
            actor=actor,
            metadata={"reason": "poll_exhausted", "poll_attempts": attempts},
        )
        return inv

    provider = inv.provider
    uf = str((provider.address or {}).get("uf") or "SP").upper()
    if isinstance(inv.fiscal_snapshot, dict):
        emit = inv.fiscal_snapshot.get("emitente") or {}
        addr = emit.get("address") or {}
        if addr.get("uf"):
            uf = str(addr["uf"]).upper()

    cnpj = "".join(ch for ch in str(getattr(provider, "document", "") or "") if ch.isdigit())
    provider_api = get_nfce_provider()
    result = provider_api.consultar(
        access_key=inv.access_key,
        receipt=n_rec,
        tp_amb=inv.tp_amb,
        context={
            "tenant": inv.tenant,
            "invoice_id": str(inv.id),
            "document_model": "65",
            "uf": uf,
            "cnpj": cnpj,
        },
    )

    prev = inv.status
    raw_meta = result.raw if isinstance(result.raw, dict) else {}
    _write_sefaz_meta(inv, poll_attempts=attempts)

    if result.status == "authorized":
        inv.status = NfceInvoice.Status.AUTHORIZED
        inv.access_key = result.access_key or inv.access_key
        inv.protocol = result.protocol or inv.protocol
        inv.rejection_code = ""
        inv.rejection_message = ""
        inv.number_consumed = True
        from apps.nfce.sefaz_timestamps import persist_authorization_meta

        persist_authorization_meta(inv, result)
    elif result.status == "rejected":
        inv.status = NfceInvoice.Status.REJECTED
        inv.rejection_code = result.rejection_code
        inv.rejection_message = result.rejection_message
        inv.number_consumed = True
    elif result.status == "polling":
        inv.status = NfceInvoice.Status.POLLING
        inv.access_key = result.access_key or inv.access_key
        inv.number_consumed = True
    else:
        permanent = (result.rejection_code or "") in {"CERT", "REF"}
        if permanent:
            inv.status = NfceInvoice.Status.FAILED
            inv.rejection_code = result.rejection_code or "failed"
            inv.rejection_message = result.rejection_message or "falha na consulta SEFAZ"
            inv.number_consumed = True
        else:
            inv.status = NfceInvoice.Status.POLLING
            inv.rejection_code = result.rejection_code or inv.rejection_code
            inv.rejection_message = result.rejection_message or inv.rejection_message
            inv.number_consumed = True

    inv.save()
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        actor=actor,
        metadata={
            "provider": provider_api.kind,
            "action": "consultar",
            "poll_attempts": attempts,
            "raw": raw_meta,
        },
    )

    if inv.status == NfceInvoice.Status.AUTHORIZED:
        from apps.nfce.artifacts import ensure_authorized_artifacts

        signed = getattr(result, "signed_xml", None)
        ensure_authorized_artifacts(
            inv,
            xml_bytes=signed if isinstance(signed, (bytes, bytearray)) else None,
        )
        from apps.food.fiscal.nfce_sync import sync_food_orders_from_nfce_invoice

        sync_food_orders_from_nfce_invoice(inv)
    elif inv.status in {
        NfceInvoice.Status.REJECTED,
        NfceInvoice.Status.FAILED,
        NfceInvoice.Status.CANCELLED,
    }:
        from apps.food.fiscal.nfce_sync import sync_food_orders_from_nfce_invoice

        sync_food_orders_from_nfce_invoice(inv)
    return inv


def schedule_nfce_poll(invoice: NfceInvoice) -> None:
    if invoice.status != NfceInvoice.Status.POLLING:
        return
    sync = bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)) or bool(
        getattr(settings, "NFCE_SYNC_POLL", False)
    )
    if sync:
        poll_nfce_invoice(invoice)
        return
    try:
        from apps.nfce.tasks import poll_nfce_invoice_task

        poll_nfce_invoice_task.apply_async(
            args=[str(invoice.tenant_id), str(invoice.id)],
            countdown=poll_countdown_seconds(),
        )
    except ImportError:
        poll_nfce_invoice(invoice)
