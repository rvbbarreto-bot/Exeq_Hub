"""Serviços NFC-e — draft → validate → emit (stub/http via port compartilhado)."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.fiscal.document_policy import DocumentModel, SaleContext, resolve_document_route
from apps.master_data.models import Provider
from apps.nfce.exceptions import (
    NfceDisabledError,
    NfceGateError,
    NfceInvalidTransitionError,
    NfcePolicyError,
    NfceValidationError,
    NfceVersionConflictError,
)
from apps.nfce.models import NfceInvoice, NfceInvoiceEvent, NfceInvoiceItem
from apps.nfce.numbering import reserve_next_number
from apps.nfce.tax import NFCE_TAX_ENGINE_VERSION, build_validation
from apps.nfe.models import NfeProduct
from apps.nfe.tax import suggest_cfop
from integrations.sefaz_nfe import get_nfce_provider


def nfce_feature_enabled() -> bool:
    return bool(getattr(settings, "NFCE_ENABLED", False))


def require_nfce_enabled() -> None:
    if not nfce_feature_enabled():
        raise NfceDisabledError("NFC-e desabilitada (NFCE_ENABLED=false)")


def require_nfce_enabled_for_tenant(tenant) -> None:
    require_nfce_enabled()
    from apps.accounts.tenant_emission import nfce_tenant_opt_in

    if not nfce_tenant_opt_in(tenant):
        raise NfceDisabledError("NFC-e não habilitada para este tenant (nfce_enabled)")


def http_mode_requires_ie() -> bool:
    return (getattr(settings, "NFCE_HTTP_MODE", "stub") or "stub").lower() == "http"


def allowed_actions(invoice: NfceInvoice) -> list[str]:
    s = invoice.status
    if s == NfceInvoice.Status.DRAFT:
        return ["validate", "emit", "replace_items"]
    if s == NfceInvoice.Status.AUTHORIZED:
        return ["download_xml", "download_pdf", "cancel"]
    if s == NfceInvoice.Status.CANCELLED:
        return ["download_xml", "download_pdf"]
    if s in {NfceInvoice.Status.REJECTED, NfceInvoice.Status.FAILED}:
        return ["discard"] if not invoice.number_consumed else []
    return []


def _record_event(
    invoice: NfceInvoice,
    *,
    from_status: str,
    to_status: str,
    actor: str = "system",
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


def resolve_checkout_route(
    *,
    provider: Provider,
    total_cents: int,
    cpf: str | None = None,
    cnpj: str | None = None,
    delivery: bool = False,
    installment: bool = False,
):
    addr = provider.address or {}
    uf = str(addr.get("uf") or addr.get("UF") or "SP").upper()
    ctx = SaleContext(
        uf=uf,
        total_cents=total_cents,
        cpf=cpf,
        cnpj=cnpj,
        delivery=delivery,
        installment=installment,
    )
    route = resolve_document_route(ctx)
    if not route.ok:
        raise NfcePolicyError(
            json.dumps(list(route.errors), ensure_ascii=False),
            code="nfce_policy",
        )
    return route


@transaction.atomic
def create_draft(
    *,
    tenant,
    provider: Provider,
    idempotency_key: str,
    issue_date: date | None = None,
    nature_operation: str = "VENDA",
    series: int = 1,
    tp_amb: str | None = None,
    identification_snapshot: dict | None = None,
    omit_dest: bool = True,
    actor: str = "api",
) -> NfceInvoice:
    require_nfce_enabled_for_tenant(tenant)
    existing = NfceInvoice.objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    if provider.tenant_id != tenant.id:
        raise NfceGateError("provider de outro tenant")
    amb = tp_amb or (getattr(settings, "NFCE_DEFAULT_TP_AMB", "2") or "2")
    inv = NfceInvoice.objects.create(
        tenant=tenant,
        provider=provider,
        idempotency_key=idempotency_key,
        issue_date=issue_date or timezone.localdate(),
        nature_operation=nature_operation[:60],
        series=series,
        tp_amb=amb,
        identification_snapshot=identification_snapshot or {},
        omit_dest=omit_dest,
        status=NfceInvoice.Status.DRAFT,
    )
    _record_event(inv, from_status="", to_status=NfceInvoice.Status.DRAFT, actor=actor)
    return inv


@transaction.atomic
def replace_items(
    invoice: NfceInvoice,
    *,
    items: list[dict[str, Any]],
    expected_version: int | None = None,
) -> NfceInvoice:
    require_nfce_enabled_for_tenant(invoice.tenant)
    if invoice.status != NfceInvoice.Status.DRAFT:
        raise NfceInvalidTransitionError("itens só em draft")
    if expected_version is not None and invoice.version != expected_version:
        raise NfceVersionConflictError(f"versão esperada {expected_version}, atual {invoice.version}")

    invoice.items.all().delete()
    emit_uf = str((invoice.provider.address or {}).get("uf") or "SP").upper()

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
                dest_uf=emit_uf,
                cfop_internal=product.cfop_internal or "5102",
                cfop_interstate=product.cfop_interstate or "6102",
            )
        else:
            cfop = suggest_cfop(emit_uf=emit_uf, dest_uf=emit_uf)
        unit = (raw.get("unit") or (product.unit if product else "UN") or "UN")[:6]
        qty = Decimal(str(raw.get("quantity") or "1"))
        unit_cents = int(
            raw.get("unit_price_cents")
            if raw.get("unit_price_cents") is not None
            else (product.unit_price_cents if product else 0)
        )
        csosn = (raw.get("csosn") or (product.csosn if product else "") or "")[:3]
        icms_cst = (raw.get("icms_cst") or (product.icms_cst if product else "") or "")[:3]
        origin = (raw.get("origin") or (product.origin if product else "0") or "0")[:1]
        NfceInvoiceItem.objects.create(
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
            discount_cents=int(raw.get("discount_cents") or 0),
            total_cents=0,
            origin=origin,
            csosn=csosn,
            icms_cst=icms_cst,
            taxes={},
        )
    invoice.version += 1
    invoice.save(update_fields=["version", "updated_at"])
    return invoice


def validate_invoice(invoice: NfceInvoice) -> dict[str, Any]:
    require_nfce_enabled_for_tenant(invoice.tenant)
    if invoice.status != NfceInvoice.Status.DRAFT:
        raise NfceInvalidTransitionError("validação só em draft")
    result = build_validation(invoice, require_ie=http_mode_requires_ie())
    for row in result["items_taxes"]:
        NfceInvoiceItem.objects.filter(
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


def _snapshot_for_emit(invoice: NfceInvoice, validation: dict[str, Any]) -> dict[str, Any]:
    from apps.nfe.catalog import CATALOG_VERSION

    provider = invoice.provider
    ident = invoice.identification_snapshot or {}
    emit_uf = str((provider.address or {}).get("uf") or "SP").upper()
    from apps.nfce.csc import resolve_csc

    csc_id, csc_token = resolve_csc(
        tenant=invoice.tenant, provider=provider, tp_amb=invoice.tp_amb
    )
    try:
        from integrations.sefaz_nfe.nfce_endpoints import resolve_nfce_endpoints

        nfce_ep = resolve_nfce_endpoints(uf=emit_uf, tp_amb=invoice.tp_amb)
        qr_base_url = nfce_ep.qr_base_url
    except ValueError:
        qr_base_url = ""
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
    dest = None
    if not invoice.omit_dest:
        doc = ident.get("document") or ident.get("cpf") or ""
        dest = {
            "document": doc,
            "document_type": "cpf",
            "name": ident.get("name") or "CONSUMIDOR",
        }
    snap = {
        "tax_engine_version": NFCE_TAX_ENGINE_VERSION,
        "catalog_version": validation.get("totals", {}).get("catalog_version") or CATALOG_VERSION,
        "layout_version": getattr(settings, "NFCE_LAYOUT_VERSION", "pl009-stub"),
        "tenant_id": str(invoice.tenant_id),
        "document_model": "65",
        "emitente": {
            "cnpj": provider.document,
            "ie": getattr(provider, "state_registration", "") or "",
            "name": provider.legal_name,
            "address": provider.address or {},
            "crt": provider.tax_regime,
        },
        "destinatario": dest,
        "header": {
            "model": "65",
            "nature": invoice.nature_operation,
            "finality": "1",
            "series": invoice.series,
            "number": invoice.number,
            "tp_amb": invoice.tp_amb,
            "issue_date": invoice.issue_date.isoformat(),
            "consumer_final": True,
            "buyer_presence": "1",
            "freight_mod": "9",
            "omit_dest": invoice.omit_dest,
            "csc_id": csc_id,
            "csc_token": csc_token,
            "qr_base_url": qr_base_url,
        },
        "sefaz": {
            "csc_id": csc_id,
            "csc_token": csc_token,
            "qr_base_url": qr_base_url,
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
def emit_nfce(
    invoice: NfceInvoice,
    *,
    expected_version: int | None = None,
    actor: str = "api",
) -> NfceInvoice:
    require_nfce_enabled_for_tenant(invoice.tenant)
    inv = NfceInvoice.objects.select_for_update().get(pk=invoice.pk)
    if expected_version is not None and inv.version != expected_version:
        raise NfceVersionConflictError(f"versão esperada {expected_version}, atual {inv.version}")
    if inv.status != NfceInvoice.Status.DRAFT:
        raise NfceInvalidTransitionError(f"não é possível emitir a partir de {inv.status}")

    from apps.nfce.gate import assert_can_emit

    assert_can_emit(
        tenant=inv.tenant,
        provider=inv.provider,
        series=inv.series,
        tp_amb=inv.tp_amb,
    )

    validation = build_validation(inv, require_ie=http_mode_requires_ie())
    if not validation["ok"]:
        raise NfceValidationError(
            json.dumps(validation["field_errors"], ensure_ascii=False),
            code="nfce_validation",
        )

    for row in validation["items_taxes"]:
        NfceInvoiceItem.objects.filter(invoice=inv, line_number=row["line_number"]).update(
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
    inv.status = NfceInvoice.Status.SUBMITTING
    inv.total_cents = validation["totals"]["total_cents"]
    if inv.payment_amount_cents is None:
        inv.payment_amount_cents = inv.total_cents
    snap = _snapshot_for_emit(inv, validation)
    snap_store = json.loads(json.dumps(snap, default=str))
    if isinstance(snap_store.get("sefaz"), dict):
        snap_store["sefaz"].pop("csc_token", None)
    if isinstance(snap_store.get("header"), dict):
        snap_store["header"].pop("csc_token", None)
    inv.fiscal_snapshot = snap_store
    inv.payload_hash = snap["payload_hash"]
    inv.taxes_summary = validation["totals"]
    inv.save()
    _record_event(inv, from_status=prev, to_status=NfceInvoice.Status.SUBMITTING, actor=actor)

    sefaz = get_nfce_provider()
    result = sefaz.emitir(
        invoice_snapshot=snap,
        context={"tenant": inv.tenant, "invoice_id": str(inv.id), "document_model": "65"},
    )

    prev = inv.status
    if result.status == "authorized":
        inv.status = NfceInvoice.Status.AUTHORIZED
        inv.access_key = result.access_key
        inv.protocol = result.protocol
        inv.number_consumed = True
        inv.rejection_code = ""
        inv.rejection_message = ""
    elif result.status == "polling":
        inv.status = NfceInvoice.Status.POLLING
        inv.access_key = result.access_key or inv.access_key
        inv.protocol = result.protocol or inv.protocol
        inv.number_consumed = True
        inv.rejection_code = result.rejection_code
        inv.rejection_message = result.rejection_message
        raw_early = result.raw if isinstance(result.raw, dict) else {}
        n_rec = str(raw_early.get("nRec") or "").strip()
        if n_rec or inv.fiscal_snapshot:
            snap = dict(inv.fiscal_snapshot or {})
            sefaz_meta = (
                dict(snap.get("sefaz") or {}) if isinstance(snap.get("sefaz"), dict) else {}
            )
            if n_rec:
                sefaz_meta["n_rec"] = n_rec
            sefaz_meta.setdefault("poll_attempts", 0)
            snap["sefaz"] = sefaz_meta
            inv.fiscal_snapshot = snap
    elif result.status == "rejected":
        inv.status = NfceInvoice.Status.REJECTED
        inv.rejection_code = result.rejection_code
        inv.rejection_message = result.rejection_message
        inv.number_consumed = True
    else:
        inv.status = NfceInvoice.Status.FAILED
        inv.rejection_code = result.rejection_code
        inv.rejection_message = result.rejection_message

    inv.save()
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        actor=actor,
        metadata={"access_key": inv.access_key, "protocol": inv.protocol},
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
    elif inv.status == NfceInvoice.Status.POLLING:
        from apps.nfce.polling import schedule_nfce_poll

        schedule_nfce_poll(inv)
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


@transaction.atomic
def cancel_nfce(
    invoice: NfceInvoice,
    *,
    justificativa: str,
    actor: str = "api",
) -> NfceInvoice:
    require_nfce_enabled_for_tenant(invoice.tenant)
    inv = NfceInvoice.objects.select_for_update().get(pk=invoice.pk)
    if inv.status != NfceInvoice.Status.AUTHORIZED:
        raise NfceInvalidTransitionError("só cancela NFC-e autorizada")
    just = (justificativa or "").strip()
    if len(just) < 15 or len(just) > 255:
        raise NfceValidationError(
            "justificativa deve ter 15–255 caracteres",
            code="nfce_validation",
        )

    cnpj = "".join(ch for ch in str(getattr(inv.provider, "document", "") or "") if ch.isdigit())
    uf = getattr(settings, "NFE_PIVOT_UF", "SP")
    if isinstance(inv.fiscal_snapshot, dict):
        addr = (inv.fiscal_snapshot.get("emitente") or {}).get("address") or {}
        if addr.get("uf"):
            uf = str(addr["uf"]).upper()
        emit_cnpj = (inv.fiscal_snapshot.get("emitente") or {}).get("cnpj")
        if emit_cnpj:
            cnpj = "".join(ch for ch in str(emit_cnpj) if ch.isdigit())

    sefaz = get_nfce_provider()
    result = sefaz.cancelar(
        access_key=inv.access_key,
        justificativa=just,
        context={
            "tenant": inv.tenant,
            "invoice_id": str(inv.id),
            "document_model": "65",
            "protocol": inv.protocol,
            "cnpj": cnpj,
            "tp_amb": inv.tp_amb,
            "uf": uf,
        },
    )

    prev = inv.status
    raw_meta = result.raw if isinstance(result.raw, dict) else {}
    if result.status == "cancelled":
        inv.status = NfceInvoice.Status.CANCELLED
        inv.protocol = result.protocol or inv.protocol
        inv.rejection_code = ""
        inv.rejection_message = ""
    else:
        inv.rejection_code = result.rejection_code or inv.rejection_code
        inv.rejection_message = result.rejection_message or "cancelamento não aceito"

    inv.save()
    _record_event(
        inv,
        from_status=prev,
        to_status=inv.status,
        actor=actor,
        metadata={"provider": sefaz.kind, "raw": raw_meta, "tpEvento": "110111"},
    )
    if inv.status == NfceInvoice.Status.CANCELLED:
        from apps.nfce.artifacts import ensure_cancelled_artifacts

        ensure_cancelled_artifacts(inv)
    return inv


def checkout_and_emit_nfce(
    *,
    tenant,
    provider: Provider,
    items: list[dict[str, Any]],
    idempotency_key: str,
    cpf: str | None = None,
    cnpj: str | None = None,
    delivery: bool = False,
    payment_method: str | None = None,
    actor: str = "pdv",
) -> NfceInvoice | dict[str, Any]:
    """
    Fluxo PDV: policy → draft → itens → emit.
    Retorna dict com route NF-e quando CNPJ (política EXEQ).
    """
    require_nfce_enabled_for_tenant(tenant)

    total_preview = 0
    for raw in items:
        unit = int(raw.get("unit_price_cents") or 0)
        qty = Decimal(str(raw.get("quantity") or "1"))
        total_preview += int((qty * Decimal(unit)).quantize(Decimal("1")))

    route = resolve_checkout_route(
        provider=provider,
        total_cents=total_preview,
        cpf=cpf,
        cnpj=cnpj,
        delivery=delivery,
    )
    if route.model == DocumentModel.NFE:
        return {
            "route": "nfe",
            "model": "55",
            "reasons": list(route.reasons),
            "message": "CNPJ exige NF-e modelo 55",
        }

    ident: dict[str, Any] = {}
    if cpf and not route.omit_dest:
        from shared.validators import validate_cpf

        ident = {"document": validate_cpf(cpf), "document_type": "cpf", "name": "CONSUMIDOR"}

    inv = create_draft(
        tenant=tenant,
        provider=provider,
        idempotency_key=idempotency_key,
        identification_snapshot=ident,
        omit_dest=route.omit_dest,
        actor=actor,
    )
    if payment_method:
        inv.payment_method = str(payment_method)[:2]
        inv.save(update_fields=["payment_method", "updated_at"])
    replace_items(inv, items=items)
    inv.refresh_from_db()
    validate_invoice(inv)
    inv.refresh_from_db()
    return emit_nfce(inv, actor=actor)
