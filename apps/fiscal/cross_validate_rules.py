"""Regras L5–L8 validação cruzada mercadorias (estudo §7)."""

from __future__ import annotations

from datetime import date
from typing import Any

# L5 — NCM capítulo × CFOP incompatível (MVP lab)
_NCM_CFOP_CONFLICTS: tuple[tuple[str, frozenset[str], str], ...] = (
    (
        "22",
        frozenset({"5101", "6101"}),
        "Capítulo 22 (bebidas) não admite CFOP de industrialização (5101/6101)",
    ),
    (
        "30",
        frozenset({"5101", "6101"}),
        "Capítulo 30 (farmacêuticos) não admite CFOP 5101/6101 para revenda comum",
    ),
)

# L6 — NCM monofásico PIS/COFINS
MONOFASIC_NCM = frozenset(
    {
        "22021000",
        "22030000",
        "33049910",
        "34011190",
        "30049099",
    }
)
MONOFASIC_PIS_CST = "04"

# L7 — ST
ST_CFOPS = frozenset({"5403", "5405", "6403", "6405"})

# L8 — RTC CRT=3 (regime normal) cutoff homolog
RTC_CRT3_CUTOFF = date(2026, 8, 3)
CRT_NORMAL = frozenset({"3", "normal", "regime_normal"})


def _err(rule: str, field: str, message: str) -> dict[str, str]:
    return {"rule": rule, "field": field, "message": message}


def validate_l5_ncm_cfop(*, ncm: str, cfop: str) -> dict[str, str] | None:
    chapter = (ncm or "")[:2]
    code = "".join(ch for ch in str(cfop or "") if ch.isdigit())
    for prefix, blocked, msg in _NCM_CFOP_CONFLICTS:
        if chapter == prefix and code in blocked:
            return _err("RULE-L5-NCM-CFOP", "cfop", msg)
    return None


def validate_l6_ncm_pis_cst(*, ncm: str, pis_cst: str, cofins_cst: str) -> dict[str, str] | None:
    ncm_digits = "".join(ch for ch in str(ncm or "") if ch.isdigit())
    if ncm_digits not in MONOFASIC_NCM:
        return None
    pis = (pis_cst or "").strip()
    cofins = (cofins_cst or "").strip()
    if pis != MONOFASIC_PIS_CST or cofins != MONOFASIC_PIS_CST:
        return _err(
            "RULE-L6-NCM-CST",
            "pis_cst",
            f"NCM {ncm_digits} monofásico exige PIS/COFINS CST {MONOFASIC_PIS_CST}",
        )
    return None


def validate_l7_st_cest(*, cfop: str, cest: str) -> dict[str, str] | None:
    code = "".join(ch for ch in str(cfop or "") if ch.isdigit())
    if code not in ST_CFOPS:
        return None
    cest_digits = "".join(ch for ch in str(cest or "") if ch.isdigit())
    if len(cest_digits) != 7:
        return _err(
            "RULE-L7-ST-CEST",
            "cest",
            f"CFOP {code} (ST) exige CEST com 7 dígitos",
        )
    return None


def validate_l8_rtc_crt3(
    *,
    crt: str,
    issue_date: date | str | None,
    rtc_mode: str,
    classification_status: str | None = None,
) -> dict[str, str] | None:
    if (rtc_mode or "").lower() != "emit":
        return None
    crt_norm = str(crt or "").strip().lower()
    if crt_norm not in CRT_NORMAL and crt_norm != "3":
        return None
    if issue_date is None:
        return None
    if isinstance(issue_date, str):
        try:
            issue_date = date.fromisoformat(issue_date[:10])
        except ValueError:
            return None
    if issue_date < RTC_CRT3_CUTOFF:
        return None
    if classification_status and classification_status != "ok":
        return _err(
            "RULE-L8-RTC-CRT3",
            "rtc",
            "CRT=3 com RTC emit exige classificação publicada após cutoff",
        )
    return None


def validate_ipi_zero(*, ipi_rate_bp: int, ipi_cst: str, ip_enq: str) -> dict[str, str] | None:
    """IPI-0: alíquota > 0 exige CST e código enquadramento."""
    if int(ipi_rate_bp or 0) <= 0:
        return None
    if not (ipi_cst or "").strip():
        return _err("RULE-IPI-0-CST", "ipi_cst", "IPI com alíquota exige CST IPI")
    if not (ip_enq or "").strip():
        return _err("RULE-IPI-0-ENQ", "ip_enq", "IPI com alíquota exige cEnq (ip_enq)")
    return None


def run_layers_l5_l8(
    *,
    ncm: str,
    cfop: str,
    pis_cst: str = "07",
    cofins_cst: str = "07",
    cest: str = "",
    crt: str = "",
    issue_date: date | str | None = None,
    rtc_mode: str = "off",
    classification_status: str | None = None,
    ipi_rate_bp: int = 0,
    ipi_cst: str = "",
    ip_enq: str = "",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fn, kwargs in (
        (validate_l5_ncm_cfop, {"ncm": ncm, "cfop": cfop}),
        (validate_l6_ncm_pis_cst, {"ncm": ncm, "pis_cst": pis_cst, "cofins_cst": cofins_cst}),
        (validate_l7_st_cest, {"cfop": cfop, "cest": cest}),
        (
            validate_l8_rtc_crt3,
            {
                "crt": crt,
                "issue_date": issue_date,
                "rtc_mode": rtc_mode,
                "classification_status": classification_status,
            },
        ),
        (validate_ipi_zero, {"ipi_rate_bp": ipi_rate_bp, "ipi_cst": ipi_cst, "ip_enq": ip_enq}),
    ):
        err = fn(**kwargs)
        if err:
            out.append(err)
    return out
