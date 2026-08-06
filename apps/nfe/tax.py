"""Motor fiscal mercadoria mínimo (SN + CST 00) — onda 1 stub-friendly."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.master_data.models import TaxRegime
from apps.nfe.models import NfeInvoice

TAX_ENGINE_VERSION = "goods-0.1.0"


def _money_cents(qty: Decimal, unit_cents: int, discount: int = 0) -> int:
    # qty * unit / 10000... wait unit is cents per unit, qty has 4 decimals
    raw = (qty * Decimal(unit_cents)).quantize(Decimal("1"))
    total = int(raw) - int(discount)
    return max(total, 0)


def calculate_item_taxes(
    *,
    tax_regime: str,
    item_total_cents: int,
    icms_rate_bp: int,
    csosn: str,
    icms_cst: str,
    origin: str,
    pis_cst: str,
    pis_rate_bp: int,
    cofins_cst: str,
    cofins_rate_bp: int,
) -> dict[str, Any]:
    taxes: dict[str, Any] = {"origin": origin}

    if tax_regime == TaxRegime.SIMPLES:
        code = (csosn or "102").zfill(3)
        taxes["icms"] = {
            "regime": "sn",
            "csosn": code,
            "base_cents": 0,
            "rate_bp": 0,
            "value_cents": 0,
        }
    else:
        cst = (icms_cst or "00").zfill(2)
        base = item_total_cents
        rate = int(icms_rate_bp or 0)
        value = base * rate // 10000 if cst == "00" else 0
        taxes["icms"] = {
            "regime": "normal",
            "cst": cst,
            "base_cents": base if cst == "00" else 0,
            "rate_bp": rate,
            "value_cents": value,
        }

    def _pc(cst: str, rate_bp: int) -> dict[str, Any]:
        r = int(rate_bp or 0)
        base = item_total_cents if r > 0 else 0
        return {
            "cst": (cst or "07")[:2],
            "base_cents": base,
            "rate_bp": r,
            "value_cents": base * r // 10000,
        }

    taxes["pis"] = _pc(pis_cst, pis_rate_bp)
    taxes["cofins"] = _pc(cofins_cst, cofins_rate_bp)
    return taxes


def build_validation(
    invoice: NfeInvoice,
    *,
    require_ie: bool,
) -> dict[str, Any]:
    """Retorna {ok, field_errors[], totals, items_taxes}."""
    errors: list[dict[str, str]] = []
    provider = invoice.provider
    customer = invoice.customer

    if not provider.document:
        errors.append({"field": "provider", "message": "emitente sem CNPJ"})
    if require_ie and not (getattr(provider, "state_registration", None) or "").strip():
        errors.append({"field": "provider.state_registration", "message": "IE do emitente obrigatória para HTTP SEFAZ"})
    addr = provider.address or {}
    if not (addr.get("uf") or addr.get("UF")):
        errors.append({"field": "provider.address.uf", "message": "UF do emitente obrigatória"})

    if not customer.document:
        errors.append({"field": "customer", "message": "destinatário sem documento"})
    c_addr = customer.address or {}
    if not (c_addr.get("logradouro") or c_addr.get("street")):
        errors.append({"field": "customer.address", "message": "endereço do destinatário incompleto"})
    if invoice.ind_ie_dest == "1":
        # IE no address ou campo futuro
        ie = (c_addr.get("ie") or c_addr.get("state_registration") or "").strip()
        if not ie:
            errors.append({"field": "customer.ie", "message": "IE do destinatário obrigatória quando indIEDest=1"})

    items = list(invoice.items.all())
    if not items:
        errors.append({"field": "items", "message": "informe ao menos um item"})

    items_taxes: list[dict[str, Any]] = []
    products_cents = 0
    icms_total = 0
    pis_total = 0
    cofins_total = 0

    regime = provider.tax_regime
    for it in items:
        if not it.ncm or len(it.ncm) < 8:
            errors.append({"field": f"items[{it.line_number}].ncm", "message": "NCM inválido"})
        if not it.cfop or len(it.cfop) != 4:
            errors.append({"field": f"items[{it.line_number}].cfop", "message": "CFOP inválido"})
        if it.quantity <= 0:
            errors.append({"field": f"items[{it.line_number}].quantity", "message": "quantidade deve ser > 0"})
        if it.unit_price_cents < 0:
            errors.append({"field": f"items[{it.line_number}].unit_price_cents", "message": "preço inválido"})

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
        products_cents += line_total
        icms_total += int(tax["icms"].get("value_cents") or 0)
        pis_total += int(tax["pis"].get("value_cents") or 0)
        cofins_total += int(tax["cofins"].get("value_cents") or 0)
        items_taxes.append(
            {
                "line_number": it.line_number,
                "total_cents": line_total,
                "taxes": tax,
            }
        )

    freight = int(invoice.freight_cents or 0)
    discount = int(invoice.discount_cents or 0)
    total = max(products_cents + freight - discount, 0)

    pay = invoice.payment_amount_cents
    if pay is not None and abs(int(pay) - total) > 1:
        errors.append(
            {
                "field": "payment_amount_cents",
                "message": f"pagamento {pay} difere do total {total}",
            }
        )

    totals = {
        "products_cents": products_cents,
        "freight_cents": freight,
        "discount_cents": discount,
        "total_cents": total,
        "icms_cents": icms_total,
        "pis_cents": pis_total,
        "cofins_cents": cofins_total,
        "tax_engine_version": TAX_ENGINE_VERSION,
    }
    return {
        "ok": len(errors) == 0,
        "field_errors": errors,
        "totals": totals,
        "items_taxes": items_taxes,
    }
