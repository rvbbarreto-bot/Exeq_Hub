"""Motor fiscal NFC-e — varejo presencial, SN + CST00."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.master_data.models import TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfce.rtc import aggregate_rtc_totals, build_item_rtc, nfce_rtc_mode
from apps.nfe.tax import (
    TAX_ENGINE_VERSION,
    _ibge_digits,
    _money_cents,
    _uf,
    calculate_item_taxes,
    validate_cfop_against_ufs,
)

NFCE_TAX_ENGINE_VERSION = f"nfce-{TAX_ENGINE_VERSION}"


def map_csosn_to_xml_group(csosn: str) -> str:
    code = (csosn or "").strip().zfill(3)
    return {
        "101": "ICMSSN101",
        "102": "ICMSSN102",
        "103": "ICMSSN102",
        "201": "ICMSSN201",
        "202": "ICMSSN202",
        "203": "ICMSSN202",
        "300": "ICMSSN102",
        "400": "ICMSSN400",
        "500": "ICMSSN500",
        "900": "ICMSSN900",
    }.get(code, "ICMSSN102")


def build_validation(
    invoice: NfceInvoice,
    *,
    require_ie: bool,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    provider = invoice.provider
    ident = invoice.identification_snapshot or {}

    if not provider.document:
        errors.append({"field": "provider", "message": "emitente sem CNPJ"})
    if require_ie and not (getattr(provider, "state_registration", None) or "").strip():
        errors.append(
            {
                "field": "provider.state_registration",
                "message": "IE do emitente obrigatória para HTTP SEFAZ",
            }
        )
    addr = provider.address or {}
    emit_uf = _uf(addr)
    if not emit_uf:
        errors.append({"field": "provider.address.uf", "message": "UF do emitente obrigatória"})
    if len(_ibge_digits(addr)) != 7:
        errors.append(
            {
                "field": "provider.address.codigo_ibge",
                "message": "código IBGE do município do emitente obrigatório (7 dígitos)",
            }
        )
    if not (addr.get("logradouro") or addr.get("street")):
        errors.append(
            {"field": "provider.address", "message": "logradouro do emitente obrigatório"}
        )
    if not getattr(provider, "tax_regime", None):
        errors.append({"field": "provider.tax_regime", "message": "CRT/regime tributário obrigatório"})

    if not invoice.omit_dest:
        doc = ident.get("document") or ident.get("cpf") or ""
        if not doc:
            errors.append(
                {"field": "identification_snapshot", "message": "CPF do consumidor obrigatório"}
            )

    items = list(invoice.items.all())
    if not items:
        errors.append({"field": "items", "message": "informe ao menos um item"})

    items_taxes: list[dict[str, Any]] = []
    products_cents = 0
    icms_total = 0
    icms_base_total = 0
    pis_total = 0
    cofins_total = 0
    regime = provider.tax_regime
    dest_uf = emit_uf

    for it in items:
        if not it.ncm or len(it.ncm) < 8:
            errors.append({"field": f"items[{it.line_number}].ncm", "message": "NCM inválido"})
        if not it.cfop or len(it.cfop) != 4:
            errors.append({"field": f"items[{it.line_number}].cfop", "message": "CFOP inválido"})
        else:
            cfop_err = validate_cfop_against_ufs(
                cfop=it.cfop, emit_uf=emit_uf, dest_uf=dest_uf
            )
            if cfop_err:
                errors.append(
                    {"field": f"items[{it.line_number}].cfop", "message": cfop_err}
                )
        if regime == TaxRegime.SIMPLES and not (it.csosn or "").strip():
            prod_csosn = ""
            if it.product_id:
                prod_csosn = (it.product.csosn or "").strip()
            if not prod_csosn:
                errors.append(
                    {
                        "field": f"items[{it.line_number}].csosn",
                        "message": "CSOSN obrigatório para Simples Nacional",
                    }
                )
        if it.quantity <= 0:
            errors.append(
                {
                    "field": f"items[{it.line_number}].quantity",
                    "message": "quantidade deve ser > 0",
                }
            )
        if it.unit_price_cents < 0:
            errors.append(
                {
                    "field": f"items[{it.line_number}].unit_price_cents",
                    "message": "preço inválido",
                }
            )

        line_total = _money_cents(it.quantity, it.unit_price_cents, it.discount_cents)
        rate_bp = 0
        csosn = it.csosn
        icms_cst = it.icms_cst
        pis_cst = "07"
        pis_bp = 0
        cofins_cst = "07"
        cofins_bp = 0
        if it.product_id:
            p = it.product
            rate_bp = p.icms_rate_bp
            csosn = csosn or p.csosn
            icms_cst = icms_cst or p.icms_cst
            pis_cst = p.pis_cst
            pis_bp = p.pis_rate_bp
            cofins_cst = p.cofins_cst
            cofins_bp = p.cofins_rate_bp

        tax = calculate_item_taxes(
            tax_regime=regime,
            item_total_cents=line_total,
            icms_rate_bp=rate_bp,
            csosn=csosn,
            icms_cst=icms_cst,
            origin=it.origin,
            pis_cst=pis_cst,
            pis_rate_bp=pis_bp,
            cofins_cst=cofins_cst,
            cofins_rate_bp=cofins_bp,
        )
        tax["rtc"] = build_item_rtc(
            line_total_cents=line_total,
            issue_date=invoice.issue_date,
        )
        if regime == TaxRegime.SIMPLES and csosn:
            tax["icms"]["xml_group"] = map_csosn_to_xml_group(csosn)

        products_cents += line_total
        icms_total += int(tax["icms"].get("value_cents") or 0)
        icms_base_total += int(tax["icms"].get("base_cents") or 0)
        pis_total += int(tax["pis"].get("value_cents") or 0)
        cofins_total += int(tax["cofins"].get("value_cents") or 0)
        items_taxes.append(
            {
                "line_number": it.line_number,
                "total_cents": line_total,
                "taxes": tax,
            }
        )

    discount = int(invoice.discount_cents or 0)
    total_cents = max(products_cents - discount, 0)

    from apps.fiscal.rtc_emit_readiness import assess_rtc_emit_readiness
    from apps.fiscal.rtc_goods import effective_payable_cents

    rtc_mode = nfce_rtc_mode()
    rtc_ready = assess_rtc_emit_readiness(
        document_model="65", issue_date=invoice.issue_date
    )
    if rtc_mode == "emit" and not rtc_ready["ok"]:
        for code in rtc_ready["blockers"]:
            errors.append({"field": "rtc", "message": f"RTC emit bloqueado: {code}"})

    totals = {
        "products_cents": products_cents,
        "discount_cents": discount,
        "freight_cents": 0,
        "icms_cents": icms_total,
        "icms_base_cents": icms_base_total,
        "pis_cents": pis_total,
        "cofins_cents": cofins_total,
        "total_cents": total_cents,
        "rtc_mode": nfce_rtc_mode(),
    }
    rtc_totals = aggregate_rtc_totals(items_taxes)
    if rtc_totals.get("v_ibs_cents") or rtc_totals.get("v_cbs_cents"):
        totals["rtc"] = rtc_totals

    pay = invoice.payment_amount_cents
    payable = effective_payable_cents(totals, mode=rtc_mode)
    if pay is not None and abs(int(pay) - payable) > 1:
        errors.append(
            {
                "field": "payment_amount_cents",
                "message": f"pagamento {pay} difere do total exigido {payable}",
            }
        )
    return {
        "ok": not errors,
        "field_errors": errors,
        "totals": totals,
        "items_taxes": items_taxes,
    }
