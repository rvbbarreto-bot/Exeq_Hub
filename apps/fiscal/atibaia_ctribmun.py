"""Mapa LC 116 → cTribMun Atibaia (LC 532/2004 — validar com contador/prefeitura)."""

from __future__ import annotations

ATIBAIA_IBGE = "3504107"

# Chave: service_code da regra (LC 116, ex. 01.07)
LC116_TO_CTRIB_MUN: dict[str, str] = {
    "01.07": "107",
    "01.01": "101",
    "01.05": "105",
    "01.06": "106",
    "01.03": "103",
    "10.05": "1005",
    "17.12": "1711",
}


def resolve_c_trib_mun(
    *,
    ibge_code: str,
    service_code: str,
    rule_c_trib_mun: str = "",
) -> str:
    """Resolve cTribMun para DPS — regra explícita ou mapa Atibaia."""
    explicit = (rule_c_trib_mun or "").strip()
    if explicit:
        return explicit
    ibge = "".join(ch for ch in (ibge_code or "") if ch.isdigit())[:7]
    code = (service_code or "").strip()
    if ibge == ATIBAIA_IBGE and code in LC116_TO_CTRIB_MUN:
        return LC116_TO_CTRIB_MUN[code]
    return ""
