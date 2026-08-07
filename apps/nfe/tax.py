"""Motor fiscal mercadoria — SN + CST00 · U5 interestadual simples (RF-23)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.master_data.models import TaxRegime
from apps.nfe.models import NfeInvoice

# U5: bump semântico — RTC hooks nulos + interestadual
TAX_ENGINE_VERSION = "goods-0.2.0-u5"

# S/SE (tabela simplificada onda 1b — RF-23)
_UF_SUL_SE = frozenset({"SP", "RJ", "ES", "MG", "PR", "SC", "RS"})


def _uf(addr: dict | None) -> str:
    if not isinstance(addr, dict):
        return ""
    return str(addr.get("uf") or addr.get("UF") or "").upper().strip()


def is_interstate(*, emit_uf: str, dest_uf: str) -> bool:
    e = (emit_uf or "").upper().strip()
    d = (dest_uf or e).upper().strip()
    if not e or not d:
        return False
    if d in {"EX", "EXTERIOR"}:
        return True
    return e != d


def default_icms_interestadual_rate_bp(*, emit_uf: str, dest_uf: str) -> int:
    """
    Alíquotas interestaduais padrão (simplificado U5 / RF-23).
    12% entre S/SE; 7% de S/SE → demais; senão 12%.
    Interno: 0 (usar rate do produto / municipal).
    """
    if not is_interstate(emit_uf=emit_uf, dest_uf=dest_uf):
        return 0
    o = (emit_uf or "").upper()
    d = (dest_uf or "").upper()
    if o in _UF_SUL_SE and d in _UF_SUL_SE:
        return 1200
    if o in _UF_SUL_SE and d not in _UF_SUL_SE:
        return 700
    return 1200


def suggest_cfop(
    *,
    emit_uf: str,
    dest_uf: str,
    cfop_internal: str = "5102",
    cfop_interstate: str = "6102",
) -> str:
    if is_interstate(emit_uf=emit_uf, dest_uf=dest_uf):
        return (cfop_interstate or "6102")[:4]
    return (cfop_internal or "5102")[:4]


def validate_cfop_against_ufs(*, cfop: str, emit_uf: str, dest_uf: str) -> str | None:
    """Retorna mensagem de erro ou None se ok (RF-05)."""
    code = (cfop or "").strip()
    if len(code) != 4 or not code.isdigit():
        return "CFOP inválido"
    inter = is_interstate(emit_uf=emit_uf, dest_uf=dest_uf)
    if inter and not code.startswith("6"):
        return f"CFOP {code} interno em operação interestadual ({emit_uf}→{dest_uf}); use 6xxx"
    if not inter and code.startswith("6"):
        return f"CFOP {code} interestadual em operação interna ({emit_uf}); use 5xxx"
    return None


def rtc_hooks_placeholder() -> dict[str, Any]:
    """U5: chaves futuras IBS/CBS (RF-25) — sem cálculo até norma/RTC."""
    return {
        "ibs": None,
        "cbs": None,
        "is": None,
        "catalog_version": None,
        "note": "RTC hooks reservados; sem cálculo em goods-0.2.0-u5",
    }


def _money_cents(qty: Decimal, unit_cents: int, discount: int = 0) -> int:
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
    emit_uf: str = "",
    dest_uf: str = "",
) -> dict[str, Any]:
    taxes: dict[str, Any] = {
        "origin": origin,
        "operation": {
            "emit_uf": (emit_uf or "").upper(),
            "dest_uf": (dest_uf or "").upper(),
            "interstate": is_interstate(emit_uf=emit_uf, dest_uf=dest_uf),
        },
        "rtc": rtc_hooks_placeholder(),
    }

    inter = is_interstate(emit_uf=emit_uf, dest_uf=dest_uf)

    if tax_regime == TaxRegime.SIMPLES:
        code = (csosn or "102").zfill(3)
        taxes["icms"] = {
            "regime": "sn",
            "csosn": code,
            "base_cents": 0,
            "rate_bp": 0,
            "value_cents": 0,
            "interstate": inter,
        }
    else:
        cst = (icms_cst or "00").zfill(2)[:2]
        base = item_total_cents
        rate = int(icms_rate_bp or 0)
        if inter and rate <= 0 and cst == "00":
            rate = default_icms_interestadual_rate_bp(emit_uf=emit_uf, dest_uf=dest_uf)
        value = base * rate // 10000 if cst == "00" else 0
        taxes["icms"] = {
            "regime": "normal",
            "cst": cst,
            "base_cents": base if cst == "00" else 0,
            "rate_bp": rate,
            "value_cents": value,
            "interstate": inter,
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

    if not customer.document:
        errors.append({"field": "customer", "message": "destinatário sem documento"})
    c_addr = customer.address or {}
    dest_uf = _uf(c_addr) or emit_uf
    if not (c_addr.get("logradouro") or c_addr.get("street")):
        errors.append({"field": "customer.address", "message": "endereço do destinatário incompleto"})
    if not _uf(c_addr):
        errors.append({"field": "customer.address.uf", "message": "UF do destinatário obrigatória"})
    if invoice.ind_ie_dest == "1":
        ie = (c_addr.get("ie") or c_addr.get("state_registration") or "").strip()
        if not ie:
            errors.append(
                {
                    "field": "customer.ie",
                    "message": "IE do destinatário obrigatória quando indIEDest=1",
                }
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
            emit_uf=emit_uf,
            dest_uf=dest_uf,
        )
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
        "icms_base_cents": icms_base_total,
        "pis_cents": pis_total,
        "cofins_cents": cofins_total,
        "tax_engine_version": TAX_ENGINE_VERSION,
        "operation": {
            "emit_uf": emit_uf,
            "dest_uf": dest_uf,
            "interstate": is_interstate(emit_uf=emit_uf, dest_uf=dest_uf),
            "id_dest": (
                "3"
                if (dest_uf or "").upper() in {"EX", "EXTERIOR"}
                else ("2" if is_interstate(emit_uf=emit_uf, dest_uf=dest_uf) else "1")
            ),
        },
    }
    return {
        "ok": len(errors) == 0,
        "field_errors": errors,
        "totals": totals,
        "items_taxes": items_taxes,
    }
