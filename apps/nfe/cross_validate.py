"""Validação cruzada cadastro produto NF-e (L1–L4)."""

from __future__ import annotations

from apps.fiscal.goods_catalog import (
    catalog_strict,
    validate_cfop_catalog,
    validate_ncm,
    validate_unit,
)
from apps.master_data.models import TaxRegime

_ORIGIN = frozenset(str(i) for i in range(9))
_PIS_COFINS_CST = frozenset({"01", "02", "03", "04", "05", "06", "07", "08", "09", "49", "99"})
_CSOSN_SN = frozenset({"101", "102", "103", "201", "202", "203", "300", "400", "500", "900"})


def validate_product_fields(
    *,
    ncm: str,
    unit: str,
    cfop_internal: str,
    cfop_interstate: str,
    csosn: str = "",
    icms_cst: str = "",
    pis_cst: str = "07",
    cofins_cst: str = "07",
    origin: str = "0",
    tax_regime: str = "",
    check_catalog: bool | None = None,
) -> list[str]:
    """Retorna lista de mensagens de erro (vazia = OK)."""
    errors: list[str] = []
    strict = catalog_strict() if check_catalog is None else check_catalog

    ncm_digits = "".join(ch for ch in str(ncm or "") if ch.isdigit())
    if len(ncm_digits) != 8:
        errors.append("NCM deve ter 8 dígitos")
    elif strict:
        err = validate_ncm(ncm_digits)
        if err:
            errors.append(err)

    unit_code = (unit or "").strip().upper()[:6]
    if not unit_code:
        errors.append("Unidade comercial obrigatória")
    elif strict:
        err = validate_unit(unit_code)
        if err:
            errors.append(err)

    cfop_int = "".join(ch for ch in str(cfop_internal or "") if ch.isdigit())
    cfop_ext = "".join(ch for ch in str(cfop_interstate or "") if ch.isdigit())
    if len(cfop_int) != 4:
        errors.append("CFOP interno deve ter 4 dígitos")
    elif not cfop_int.startswith("5"):
        errors.append("CFOP interno deve iniciar com 5 (operação interna)")
    elif strict:
        err = validate_cfop_catalog(cfop_int)
        if err:
            errors.append(err)

    if len(cfop_ext) != 4:
        errors.append("CFOP interestadual deve ter 4 dígitos")
    elif not cfop_ext.startswith("6"):
        errors.append("CFOP interestadual deve iniciar com 6 (operação interestadual)")
    elif strict:
        err = validate_cfop_catalog(cfop_ext)
        if err:
            errors.append(err)

    orig = (origin or "0")[:1]
    if orig not in _ORIGIN:
        errors.append("Origem da mercadoria deve ser 0–8")

    csosn_val = (csosn or "").strip()
    icms_val = (icms_cst or "").strip()
    regime = (tax_regime or "").strip()
    is_sn = regime == TaxRegime.SIMPLES or (not regime and csosn_val)

    if is_sn:
        if not csosn_val:
            errors.append("CSOSN obrigatório para Simples Nacional")
        elif csosn_val not in _CSOSN_SN:
            errors.append(f"CSOSN {csosn_val} inválido para SN")
        if icms_val:
            errors.append("Não informe CST ICMS quando CSOSN estiver preenchido (SN)")
    elif icms_val and len(icms_val) not in {2, 3}:
        errors.append("CST ICMS inválido")

    for label, cst in (("PIS", pis_cst), ("COFINS", cofins_cst)):
        code = (cst or "").strip()
        if code and code not in _PIS_COFINS_CST:
            errors.append(f"CST {label} {code} inválido")

    return errors
