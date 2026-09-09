"""Validação cruzada NF-e — L1–L8 + ST/IPI."""

from __future__ import annotations

from datetime import date
from typing import Any, TypedDict

from django.conf import settings

from apps.fiscal.cross_validate_rules import run_layers_l5_l8
from apps.fiscal.goods_catalog import (
    catalog_strict,
    validate_cfop_catalog,
    validate_ncm,
    validate_unit,
)
from apps.fiscal.goods_validate import (
    CrossValidateContext,
    effective_cross_validate_mode,
    tenant_fiscal_profile,
    validate_fiscal_profile_item,
    validate_fiscal_profile_product,
)
from apps.fiscal.rtc_goods import nfe_rtc_mode, resolve_goods_classification
from apps.master_data.models import TaxRegime

_ORIGIN = frozenset(str(i) for i in range(9))
_PIS_COFINS_CST = frozenset({"01", "02", "03", "04", "05", "06", "07", "08", "09", "49", "99"})
_CSOSN_SN = frozenset({"101", "102", "103", "201", "202", "203", "300", "400", "500", "900"})


class CrossValidationResult(TypedDict):
    ok: bool
    errors: list[dict[str, str]]
    warnings: list[dict[str, str]]
    fiscal_complete: bool


def cross_validate_mode(
    *,
    context: CrossValidateContext = "draft",
    http_emit: bool = False,
) -> str:
    return effective_cross_validate_mode(context=context, http_emit=http_emit)


def _msg_errors(messages: list[str], *, rule: str, field: str) -> list[dict[str, str]]:
    return [{"rule": rule, "field": field, "message": m} for m in messages]


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
    cest: str = "",
    ipi_cst: str = "",
    ip_enq: str = "",
    ipi_rate_bp: int = 0,
    issue_date: date | str | None = None,
    crt: str = "",
    check_catalog: bool | None = None,
    tenant=None,
    context: CrossValidateContext = "catalog",
    http_emit: bool = False,
) -> list[str]:
    """Compat — retorna só mensagens de erro bloqueantes (L1–L4 + L5–L8)."""
    result = cross_validate_product(
        ncm=ncm,
        unit=unit,
        cfop_internal=cfop_internal,
        cfop_interstate=cfop_interstate,
        csosn=csosn,
        icms_cst=icms_cst,
        pis_cst=pis_cst,
        cofins_cst=cofins_cst,
        origin=origin,
        tax_regime=tax_regime,
        cest=cest,
        ipi_cst=ipi_cst,
        ip_enq=ip_enq,
        ipi_rate_bp=ipi_rate_bp,
        issue_date=issue_date,
        crt=crt,
        check_catalog=check_catalog,
        tenant=tenant,
        context=context,
        http_emit=http_emit,
    )
    return [e["message"] for e in result["errors"]]


def cross_validate_product(
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
    cest: str = "",
    ipi_cst: str = "",
    ip_enq: str = "",
    ipi_rate_bp: int = 0,
    issue_date: date | str | None = None,
    crt: str = "",
    check_catalog: bool | None = None,
    tenant=None,
    context: CrossValidateContext = "draft",
    http_emit: bool = False,
) -> CrossValidationResult:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    strict = catalog_strict() if check_catalog is None else check_catalog

    profile = tenant_fiscal_profile(tenant)
    errors.extend(
        validate_fiscal_profile_product(
            fiscal_profile=profile,
            cfop_internal=cfop_internal,
            cfop_interstate=cfop_interstate,
            csosn=csosn,
        )
    )
    ncm_digits = "".join(ch for ch in str(ncm or "") if ch.isdigit())
    if len(ncm_digits) != 8:
        errors.extend(_msg_errors(["NCM deve ter 8 dígitos"], rule="RULE-L1-NCM", field="ncm"))
    elif strict:
        err = validate_ncm(ncm_digits)
        if err:
            errors.extend(_msg_errors([err], rule="RULE-L2-CATALOG-NCM", field="ncm"))

    unit_code = (unit or "").strip().upper()[:6]
    if not unit_code:
        errors.extend(_msg_errors(["Unidade comercial obrigatória"], rule="RULE-L1-UNIT", field="unit"))
    elif strict:
        err = validate_unit(unit_code)
        if err:
            errors.extend(_msg_errors([err], rule="RULE-L2-CATALOG-UNIT", field="unit"))

    cfop_int = "".join(ch for ch in str(cfop_internal or "") if ch.isdigit())
    cfop_ext = "".join(ch for ch in str(cfop_interstate or "") if ch.isdigit())
    if len(cfop_int) != 4:
        errors.append(
            {"rule": "RULE-L1-CFOP", "field": "cfop_internal", "message": "CFOP interno deve ter 4 dígitos"}
        )
    elif not cfop_int.startswith("5"):
        errors.append(
            {
                "rule": "RULE-L4-CFOP-SCOPE",
                "field": "cfop_internal",
                "message": "CFOP interno deve iniciar com 5 (operação interna)",
            }
        )
    elif strict:
        err = validate_cfop_catalog(cfop_int)
        if err:
            errors.extend(_msg_errors([err], rule="RULE-L2-CATALOG-CFOP", field="cfop_internal"))

    if len(cfop_ext) != 4:
        errors.append(
            {
                "rule": "RULE-L1-CFOP",
                "field": "cfop_interstate",
                "message": "CFOP interestadual deve ter 4 dígitos",
            }
        )
    elif not cfop_ext.startswith("6"):
        errors.append(
            {
                "rule": "RULE-L4-CFOP-SCOPE",
                "field": "cfop_interstate",
                "message": "CFOP interestadual deve iniciar com 6 (operação interestadual)",
            }
        )
    elif strict:
        err = validate_cfop_catalog(cfop_ext)
        if err:
            errors.extend(_msg_errors([err], rule="RULE-L2-CATALOG-CFOP", field="cfop_interstate"))

    orig = (origin or "0")[:1]
    if orig not in _ORIGIN:
        errors.append({"rule": "RULE-L1-ORIGIN", "field": "origin", "message": "Origem da mercadoria deve ser 0–8"})

    csosn_val = (csosn or "").strip()
    icms_val = (icms_cst or "").strip()
    regime = (tax_regime or "").strip()
    is_sn = regime == TaxRegime.SIMPLES or (not regime and csosn_val)

    if is_sn:
        if not csosn_val:
            errors.append({"rule": "RULE-L3-SN", "field": "csosn", "message": "CSOSN obrigatório para Simples Nacional"})
        elif csosn_val not in _CSOSN_SN:
            errors.append(
                {"rule": "RULE-L3-SN", "field": "csosn", "message": f"CSOSN {csosn_val} inválido para SN"}
            )
        if icms_val:
            errors.append(
                {
                    "rule": "RULE-L3-SN",
                    "field": "icms_cst",
                    "message": "Não informe CST ICMS quando CSOSN estiver preenchido (SN)",
                }
            )
    elif icms_val and len(icms_val) not in {2, 3}:
        errors.append({"rule": "RULE-L3-CST", "field": "icms_cst", "message": "CST ICMS inválido"})

    for label, cst, field in (
        ("PIS", pis_cst, "pis_cst"),
        ("COFINS", cofins_cst, "cofins_cst"),
    ):
        code = (cst or "").strip()
        if code and code not in _PIS_COFINS_CST:
            errors.append(
                {"rule": "RULE-L3-CST", "field": field, "message": f"CST {label} {code} inválido"}
            )

    rtc_mode = nfe_rtc_mode()
    cls_status = resolve_goods_classification().get("status")
    seen_cfops: set[str] = set()
    for cfop_code in (cfop_int, cfop_ext):
        if not cfop_code or cfop_code in seen_cfops:
            continue
        seen_cfops.add(cfop_code)
        errors.extend(
            run_layers_l5_l8(
                ncm=ncm_digits,
                cfop=cfop_code,
                pis_cst=pis_cst,
                cofins_cst=cofins_cst,
                cest=cest,
                crt=crt,
                issue_date=issue_date,
                rtc_mode=rtc_mode,
                classification_status=cls_status,
                ipi_rate_bp=ipi_rate_bp,
                ipi_cst=ipi_cst,
                ip_enq=ip_enq,
            )
        )

    mode = cross_validate_mode(context=context, http_emit=http_emit)
    if mode == "off":
        return {"ok": True, "errors": [], "warnings": warnings, "fiscal_complete": True}

    hard_rules = {
        "RULE-L1-NCM",
        "RULE-L2-CATALOG-NCM",
        "RULE-L1-UNIT",
        "RULE-L2-CATALOG-UNIT",
        "RULE-L1-CFOP",
        "RULE-L2-CATALOG-CFOP",
        "RULE-L4-CFOP-SCOPE",
        "RULE-L1-ORIGIN",
        "RULE-L3-SN",
        "RULE-L3-CST",
        "RULE-L7-ST-CEST",
        "RULE-IPI-0-CST",
        "RULE-IPI-0-ENQ",
        "RULE-L8-RTC-CRT3",
        "RULE-PROFILE-ST",
    }
    if mode == "warn":
        kept: list[dict[str, str]] = []
        for err in errors:
            if err.get("rule") in hard_rules:
                kept.append(err)
            else:
                warnings.append(err)
        errors = kept

    fiscal_complete = len(errors) == 0 and len(warnings) == 0
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "fiscal_complete": fiscal_complete,
    }


def cross_validate_invoice_item(
    *,
    line_number: int,
    ncm: str,
    cfop: str,
    pis_cst: str,
    cofins_cst: str,
    cest: str = "",
    csosn: str = "",
    ipi_cst: str = "",
    ip_enq: str = "",
    ipi_rate_bp: int = 0,
    issue_date: date | str | None,
    crt: str,
    tenant=None,
    context: CrossValidateContext = "emit",
    http_emit: bool = False,
) -> CrossValidationResult:
    """Validação L5–L8 por linha de NF-e/NFC-e (emit)."""
    mode = cross_validate_mode(context=context, http_emit=http_emit)
    if mode == "off":
        return {"ok": True, "errors": [], "warnings": [], "fiscal_complete": True}

    errors = list(
        validate_fiscal_profile_item(
            fiscal_profile=tenant_fiscal_profile(tenant),
            cfop=cfop,
            csosn=csosn,
            line_number=line_number,
        )
    )
    errors.extend(
        run_layers_l5_l8(
            ncm=ncm,
            cfop=cfop,
            pis_cst=pis_cst,
            cofins_cst=cofins_cst,
            cest=cest,
            crt=crt,
            issue_date=issue_date,
            rtc_mode=nfe_rtc_mode(),
            classification_status=resolve_goods_classification().get("status"),
            ipi_rate_bp=ipi_rate_bp,
            ipi_cst=ipi_cst,
            ip_enq=ip_enq,
        )
    )
    for err in errors:
        if not str(err.get("field") or "").startswith("items["):
            err["field"] = f"items[{line_number}].{err.get('field', 'cfop')}"
    warnings: list[dict[str, str]] = []
    if mode == "warn":
        hard = {
            "RULE-L7-ST-CEST",
            "RULE-IPI-0-CST",
            "RULE-IPI-0-ENQ",
            "RULE-L8-RTC-CRT3",
            "RULE-PROFILE-ST",
        }
        kept: list[dict[str, str]] = []
        for err in errors:
            if err.get("rule") in hard:
                kept.append(err)
            else:
                warnings.append(err)
        errors = kept
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "fiscal_complete": len(errors) == 0 and len(warnings) == 0,
    }
