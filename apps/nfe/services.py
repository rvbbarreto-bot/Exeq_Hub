from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.master_data.models import Customer, Provider
from apps.nfe.exceptions import (
    NfeDisabledError,
    NfeGateError,
    NfeInvalidTransitionError,
    NfeValidationError,
    NfeVersionConflictError,
)
from apps.nfe.models import NfeInvoice, NfeInvoiceEvent, NfeInvoiceItem, NfeProduct
from apps.nfe.numbering import reserve_next_number
from apps.nfe.tax import TAX_ENGINE_VERSION, build_validation
from integrations.sefaz_nfe import get_nfe_provider


def nfe_feature_enabled() -> bool:
    return bool(getattr(settings, "NFE_ENABLED", False))


def require_nfe_enabled() -> None:
    if not nfe_feature_enabled():
        raise NfeDisabledError("NF-e desabilitada (NFE_ENABLED=false)")


def http_mode_requires_ie() -> bool:
    return (getattr(settings, "NFE_HTTP_MODE", "stub") or "stub").lower() == "http"


def _record_event(
    invoice: NfeInvoice,
    *,
    from_status: str,
    to_status: str,
    actor: str = "system",
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


def allowed_actions(invoice: NfeInvoice) -> list[str]:
    from apps.nfe.artifacts import has_danfe_pdf, has_xml_authorized

    s = invoice.status
    actions: list[str] = ["refresh"]
    if s == NfeInvoice.Status.DRAFT:
        actions += ["edit", "validate", "emit", "discard"]
    if s in {NfeInvoice.Status.REJECTED, NfeInvoice.Status.FAILED} and not invoice.number_consumed:
        actions += ["edit", "validate", "emit"]
    if s in {NfeInvoice.Status.REJECTED, NfeInvoice.Status.FAILED} and invoice.number_consumed:
        actions.append("clone")
    if s == NfeInvoice.Status.AUTHORIZED:
        actions.append("cancel")
    if s in {NfeInvoice.Status.AUTHORIZED, NfeInvoice.Status.CANCELLED}:
        if has_xml_authorized(invoice):
            actions.append("download_xml")
        if has_danfe_pdf(invoice):
            actions.append("download_pdf")
    return actions


@transaction.atomic
def discard_draft(
    invoice: NfeInvoice,
    *,
    actor: str = "api",
) -> None:
    """Remove rascunho puro (sem número consumido)."""
    require_nfe_enabled()
    if invoice.status != NfeInvoice.Status.DRAFT:
        raise NfeInvalidTransitionError("discard só em draft")
    if invoice.number_consumed or invoice.number is not None:
        raise NfeInvalidTransitionError("draft com número — use clone/cancel se aplicável")
    _record_event(
        invoice,
        from_status=invoice.status,
        to_status="discarded",
        actor=actor,
        metadata={"reason": "operator_discard"},
    )
    invoice.delete()


@transaction.atomic
def clone_invoice(
    source: NfeInvoice,
    *,
    idempotency_key: str,
    actor: str = "api",
) -> NfeInvoice:
    """Novo draft a partir de rejected/failed com nNF consumido (sem reusar number)."""
    require_nfe_enabled()
    if source.status not in {NfeInvoice.Status.REJECTED, NfeInvoice.Status.FAILED}:
        raise NfeInvalidTransitionError("clone só a partir de rejected/failed")
    if not source.number_consumed:
        raise NfeInvalidTransitionError("clone desnecessário — reabra a nota sem número consumido")
    inv = create_draft(
        tenant=source.tenant,
        provider=source.provider,
        customer=source.customer,
        idempotency_key=idempotency_key,
        nature_operation=source.nature_operation or "VENDA",
        series=source.series or 1,
        tp_amb=source.tp_amb,
        ind_ie_dest=source.ind_ie_dest or "9",
        issue_date=timezone.localdate(),
        actor=actor,
    )
    if inv.id != source.id and not inv.items.exists():
        source_items = list(source.items.order_by("line_number"))
        if source_items:
            payload = []
            for it in source_items:
                row: dict[str, Any] = {
                    "code": it.code,
                    "description": it.description,
                    "ncm": it.ncm,
                    "cfop": it.cfop,
                    "unit": it.unit,
                    "quantity": str(it.quantity),
                    "unit_price_cents": it.unit_price_cents,
                    "discount_cents": it.discount_cents,
                    "origin": it.origin,
                    "csosn": it.csosn,
                    "icms_cst": it.icms_cst,
                }
                if it.product_id:
                    row["product_id"] = str(it.product_id)
                payload.append(row)
            replace_items(inv, items=payload)
    inv.freight_cents = source.freight_cents or 0
    inv.discount_cents = source.discount_cents or 0
    inv.payment_method = source.payment_method or ""
    inv.payment_amount_cents = source.payment_amount_cents
    inv.nature_operation = source.nature_operation
    inv.save(
        update_fields=[
            "freight_cents",
            "discount_cents",
            "payment_method",
            "payment_amount_cents",
            "nature_operation",
            "updated_at",
        ]
    )
    _record_event(
        inv,
        from_status=NfeInvoice.Status.DRAFT,
        to_status=NfeInvoice.Status.DRAFT,
        actor=actor,
        metadata={"cloned_from": str(source.id)},
    )
    return inv



@transaction.atomic
def create_draft(
    *,
    tenant,
    provider: Provider,
    customer: Customer,
    idempotency_key: str,
    issue_date: date | None = None,
    nature_operation: str = "VENDA",
    series: int = 1,
    tp_amb: str | None = None,
    ind_ie_dest: str = "9",
    actor: str = "api",
) -> NfeInvoice:
    require_nfe_enabled()
    existing = NfeInvoice.objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    if provider.tenant_id != tenant.id or customer.tenant_id != tenant.id:
        raise NfeGateError("provider/customer de outro tenant")
    amb = tp_amb or (getattr(settings, "NFE_DEFAULT_TP_AMB", "2") or "2")
    inv = NfeInvoice.objects.create(
        tenant=tenant,
        provider=provider,
        customer=customer,
        idempotency_key=idempotency_key,
        issue_date=issue_date or timezone.localdate(),
        nature_operation=nature_operation[:60],
        series=series,
        tp_amb=amb,
        ind_ie_dest=ind_ie_dest,
        status=NfeInvoice.Status.DRAFT,
    )
    _record_event(inv, from_status="", to_status=NfeInvoice.Status.DRAFT, actor=actor)
    return inv


@transaction.atomic
def replace_items(
    invoice: NfeInvoice,
    *,
    items: list[dict[str, Any]],
    expected_version: int | None = None,
) -> NfeInvoice:
    require_nfe_enabled()
    if invoice.status != NfeInvoice.Status.DRAFT and not (
        invoice.status in {NfeInvoice.Status.REJECTED, NfeInvoice.Status.FAILED}
        and not invoice.number_consumed
    ):
        raise NfeInvalidTransitionError("itens só em draft/rejeitada sem número consumido")
    if expected_version is not None and invoice.version != expected_version:
        raise NfeVersionConflictError(f"versão esperada {expected_version}, atual {invoice.version}")

    invoice.items.all().delete()
    emit_uf = str((invoice.provider.address or {}).get("uf") or "").upper()
    dest_uf = str((invoice.customer.address or {}).get("uf") or emit_uf).upper()
    from apps.nfe.tax import suggest_cfop

    for idx, raw in enumerate(items, start=1):
        product = None
        product_id = raw.get("product_id")
        if product_id:
            product = NfeProduct.objects.filter(tenant_id=invoice.tenant_id, id=product_id).first()
        code = (raw.get("code") or (product.code if product else "") or f"ITEM{idx}")[:60]
        description = (
            raw.get("description") or (product.description if product else "") or code
        )[:120]
        ncm = (raw.get("ncm") or (product.ncm if product else "") or "")[:8]
        if raw.get("cfop"):
            cfop = str(raw.get("cfop"))[:4]
        elif product:
            cfop = suggest_cfop(
                emit_uf=emit_uf,
                dest_uf=dest_uf,
                cfop_internal=product.cfop_internal or "5102",
                cfop_interstate=product.cfop_interstate or "6102",
            )
        else:
            cfop = suggest_cfop(emit_uf=emit_uf, dest_uf=dest_uf)
        unit = (raw.get("unit") or (product.unit if product else "UN") or "UN")[:6]
        qty = Decimal(str(raw.get("quantity") or "1"))
        unit_cents = int(
            raw.get("unit_price_cents")
            if raw.get("unit_price_cents") is not None
            else (product.unit_price_cents if product else 0)
        )
        discount = int(raw.get("discount_cents") or 0)
        total = int((qty * Decimal(unit_cents)).quantize(Decimal("1"))) - discount
        total = max(total, 0)
        origin = (raw.get("origin") or (product.origin if product else "0") or "0")[:1]
        csosn = (raw.get("csosn") or (product.csosn if product else "") or "")[:3]
        icms_cst = (raw.get("icms_cst") or (product.icms_cst if product else "") or "")[:3]
        NfeInvoiceItem.objects.create(
            invoice=invoice,
            line_number=idx,
            product=product,
            code=code,
            description=description,
            ncm=ncm,
            cfop=cfop,
            unit=unit,
            quantity=qty,
            unit_price_cents=unit_cents,
            discount_cents=discount,
            total_cents=total,
            origin=origin,
            csosn=csosn,
            icms_cst=icms_cst,
            taxes={},
        )
    invoice.version += 1
    invoice.save(update_fields=["version", "updated_at"])
    return invoice


def validate_invoice(invoice: NfeInvoice) -> dict[str, Any]:
    require_nfe_enabled()
    result = build_validation(invoice, require_ie=http_mode_requires_ie())
    for row in result["items_taxes"]:
        NfeInvoiceItem.objects.filter(
            invoice=invoice, line_number=row["line_number"]
        ).update(taxes=row["taxes"], total_cents=row["total_cents"])
    invoice.total_cents = result["totals"]["total_cents"]
    invoice.taxes_summary = result["totals"]
    invoice.last_validation = {
        "ok": result["ok"],
        "field_errors": result["field_errors"],
        "at": timezone.now().isoformat(),
    }
    invoice.version += 1
    invoice.save(
        update_fields=[
            "total_cents",
            "taxes_summary",
            "last_validation",
            "version",
            "updated_at",
        ]
    )
    return result


def _snapshot_for_emit(invoice: NfeInvoice, validation: dict[str, Any]) -> dict[str, Any]:
    provider = invoice.provider
    customer = invoice.customer
    items = []
    for it in invoice.items.all():
        items.append(
            {
                "line": it.line_number,
                "code": it.code,
                "description": it.description,
                "ncm": it.ncm,
                "cfop": it.cfop,
                "unit": it.unit,
                "quantity": str(it.quantity),
                "unit_price_cents": it.unit_price_cents,
                "total_cents": it.total_cents,
                "origin": it.origin,
                "csosn": it.csosn,
                "icms_cst": it.icms_cst,
                "taxes": it.taxes,
            }
        )
    snap = {
        "tax_engine_version": TAX_ENGINE_VERSION,
        "layout_version": getattr(settings, "NFE_LAYOUT_VERSION", "pl009-stub"),
        "tenant_id": str(invoice.tenant_id),
        "emitente": {
            "cnpj": provider.document,
            "ie": getattr(provider, "state_registration", "") or "",
            "name": provider.legal_name,
            "address": provider.address or {},
            "crt": provider.tax_regime,
        },
        "destinatario": {
            "document": customer.document,
            "document_type": customer.document_type,
            "name": customer.name,
            "address": customer.address or {},
            "ind_ie_dest": invoice.ind_ie_dest,
        },
        "header": {
            "nature": invoice.nature_operation,
            "finality": invoice.finality,
            "series": invoice.series,
            "number": invoice.number,
            "tp_amb": invoice.tp_amb,
            "issue_date": invoice.issue_date.isoformat(),
            "ind_ie_dest": invoice.ind_ie_dest,
            "consumer_final": invoice.consumer_final,
            "buyer_presence": invoice.buyer_presence,
            "freight_mod": invoice.freight_mod,
        },
        "items": items,
        "totals": validation["totals"],
        "payment": {
            "method": invoice.payment_method,
            "amount_cents": invoice.payment_amount_cents or validation["totals"]["total_cents"],
        },
    }
    raw = json.dumps(snap, sort_keys=True, default=str).encode("utf-8")
    snap["payload_hash"] = hashlib.sha256(raw).hexdigest()
    return snap


@transaction.atomic
def emit_invoice(
    invoice: NfeInvoice,
    *,
    expected_version: int | None = None,
    actor: str = "api",
) -> NfeInvoice:
    require_nfe_enabled()
    inv = NfeInvoice.objects.select_for_update().get(pk=invoice.pk)
    if expected_version is not None and inv.version != expected_version:
        raise NfeVersionConflictError(f"versão esperada {expected_version}, atual {inv.version}")
    if inv.status not in {
        NfeInvoice.Status.DRAFT,
        NfeInvoice.Status.REJECTED,
        NfeInvoice.Status.FAILED,
    }:
        raise NfeInvalidTransitionError(f"não é possível emitir a partir de {inv.status}")
    if inv.number_consumed and inv.status != NfeInvoice.Status.DRAFT:
        raise NfeInvalidTransitionError("número já consumido — clone required")

    validation = build_validation(inv, require_ie=http_mode_requires_ie())
    if not validation["ok"]:
        raise NfeValidationError(
            json.dumps(validation["field_errors"], ensure_ascii=False),
            code="nfe_validation",
        )

    # Atualiza totais nos items
    for row in validation["items_taxes"]:
        NfeInvoiceItem.objects.filter(invoice=inv, line_number=row["line_number"]).update(
            taxes=row["taxes"], total_cents=row["total_cents"]
        )

    if inv.number is None:
        inv.number = reserve_next_number(
            tenant_id=inv.tenant_id,
            provider_id=inv.provider_id,
            series=inv.series,
            tp_amb=inv.tp_amb,
        )

    prev = inv.status
    inv.status = NfeInvoice.Status.SUBMITTING
    inv.total_cents = validation["totals"]["total_cents"]
    if inv.payment_amount_cents is None:
        inv.payment_amount_cents = inv.total_cents
    snap = _snapshot_for_emit(inv, validation)
    inv.fiscal_snapshot = snap
    inv.payload_hash = snap["payload_hash"]
    inv.taxes_summary = validation["totals"]
    inv.save()
    _record_event(inv, from_status=prev, to_status=NfeInvoice.Status.SUBMITTING, actor=actor)

    sefaz = get_nfe_provider()
    result = sefaz.emitir(
        invoice_snapshot=snap,
        context={"tenant": inv.tenant, "invoice_id": str(inv.id)},
    )

    prev = inv.status
    if result.status == "authorized":
        inv.status = NfeInvoice.Status.AUTHORIZED
        inv.access_key = result.access_key
        inv.protocol = result.protocol
        inv.number_consumed = True
        inv.rejection_code = ""
        inv.rejection_message = ""
    elif result.status == "polling":
        inv.status = NfeInvoice.Status.POLLING
        inv.access_key = result.access_key or inv.access_key
        inv.protocol = result.protocol or inv.protocol
        inv.number_consumed = True
        inv.rejection_code = result.rejection_code
        inv.rejection_message = result.rejection_message
        # I5: recibo (nRec) para retAutorização — sem re-reservar série
        raw_early = result.raw if isinstance(result.raw, dict) else {}
        n_rec = str(raw_early.get("nRec") or "").strip()
        if n_rec or inv.fiscal_snapshot:
            snap = dict(inv.fiscal_snapshot or {})
            sefaz_meta = dict(snap.get("sefaz") or {}) if isinstance(snap.get("sefaz"), dict) else {}
            if n_rec:
                sefaz_meta["n_rec"] = n_rec
            sefaz_meta.setdefault("poll_attempts", 0)
            snap["sefaz"] = sefaz_meta
            inv.fiscal_snapshot = snap
    elif result.status == "rejected":
        inv.status = NfeInvoice.Status.REJECTED
        inv.access_key = result.access_key or inv.access_key
        inv.rejection_code = result.rejection_code
        inv.rejection_message = result.rejection_message
        inv.number_consumed = True
    else:
        inv.status = NfeInvoice.Status.FAILED
        inv.access_key = result.access_key or inv.access_key
        inv.rejection_code = result.rejection_code or "failed"
        inv.rejection_message = result.rejection_message or "falha na autorização"
        # número reservado: em HTTP falhou após POST pode ter sido consumido; conservador = True se key
        if inv.access_key:
            inv.number_consumed = True
    inv.version += 1
    inv.save()
    raw_meta = result.raw if isinstance(result.raw, dict) else {}
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        actor=actor,
        metadata={"provider": sefaz.kind, "raw": raw_meta},
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
    elif inv.status == NfeInvoice.Status.POLLING:
        from apps.nfe.polling import schedule_nfe_poll

        schedule_nfe_poll(inv)
    return inv


@transaction.atomic
def cancel_invoice(
    invoice: NfeInvoice,
    *,
    justificativa: str,
    actor: str = "api",
) -> NfeInvoice:
    require_nfe_enabled()
    inv = NfeInvoice.objects.select_for_update().get(pk=invoice.pk)
    if inv.status != NfeInvoice.Status.AUTHORIZED:
        raise NfeInvalidTransitionError("só cancela NF-e autorizada")
    just = (justificativa or "").strip()
    if len(just) < 15 or len(just) > 255:
        raise NfeValidationError("justificativa deve ter 15–255 caracteres")

    prev = inv.status
    inv.status = NfeInvoice.Status.CANCEL_REQUESTED
    inv.save(update_fields=["status", "updated_at"])
    _record_event(inv, from_status=prev, to_status=inv.status, actor=actor)

    cnpj = "".join(ch for ch in str(getattr(inv.provider, "document", "") or "") if ch.isdigit())
    uf = getattr(settings, "NFE_PIVOT_UF", "SP")
    if isinstance(inv.fiscal_snapshot, dict):
        addr = (inv.fiscal_snapshot.get("emitente") or {}).get("address") or {}
        if addr.get("uf"):
            uf = str(addr["uf"]).upper()
        emit_cnpj = (inv.fiscal_snapshot.get("emitente") or {}).get("cnpj")
        if emit_cnpj:
            cnpj = "".join(ch for ch in str(emit_cnpj) if ch.isdigit())

    sefaz = get_nfe_provider()
    result = sefaz.cancelar(
        access_key=inv.access_key,
        justificativa=just,
        context={
            "tenant": inv.tenant,
            "invoice_id": str(inv.id),
            "protocol": inv.protocol,
            "cnpj": cnpj,
            "tp_amb": inv.tp_amb,
            "uf": uf,
        },
    )
    prev = inv.status
    raw_meta = result.raw if isinstance(result.raw, dict) else {}
    if result.status == "cancelled":
        inv.status = NfeInvoice.Status.CANCELLED
        inv.protocol = result.protocol or inv.protocol
        inv.rejection_code = ""
        inv.rejection_message = ""
    else:
        inv.status = NfeInvoice.Status.AUTHORIZED
        inv.rejection_code = result.rejection_code or inv.rejection_code
        inv.rejection_message = result.rejection_message or "cancelamento não aceito"
    inv.version += 1
    inv.save()
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        actor=actor,
        metadata={"provider": sefaz.kind, "raw": raw_meta, "tpEvento": "110111"},
    )
    if inv.status == NfeInvoice.Status.CANCELLED:
        from apps.nfe.artifacts import ensure_cancel_xml, ensure_danfe_pdf

        signed = getattr(result, "signed_xml", None)
        ensure_cancel_xml(
            inv,
            xml_bytes=signed if isinstance(signed, (bytes, bytearray)) else None,
            provider_raw=raw_meta,
        )
        # DANFE com tarja cancelada (best-effort; não reverte cancelled)
        ensure_danfe_pdf(inv, cancelled=True)
        from apps.nfe.outbox import publish_after_terminal_status

        publish_after_terminal_status(inv)
    return inv


def create_product(
    *,
    tenant,
    code: str,
    description: str,
    ncm: str,
    unit_price_cents: int = 0,
    unit: str = "UN",
    origin: str = "0",
    cfop_internal: str = "5102",
    cfop_interstate: str = "6102",
    csosn: str = "102",
    icms_cst: str = "",
    icms_rate_bp: int = 0,
    tax_regime_hint: str = "",
) -> NfeProduct:
    require_nfe_enabled()
    return NfeProduct.objects.create(
        tenant=tenant,
        code=code[:60],
        description=description[:120],
        ncm=ncm[:8],
        unit=unit[:6],
        unit_price_cents=unit_price_cents,
        origin=origin[:1],
        cfop_internal=cfop_internal[:4],
        cfop_interstate=(cfop_interstate or "6102")[:4],
        csosn=csosn[:3],
        icms_cst=icms_cst[:3],
        icms_rate_bp=icms_rate_bp,
    )
