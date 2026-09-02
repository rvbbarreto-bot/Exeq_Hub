"""Mapa LC 116 → cTribMun Atibaia.

ATENÇÃO: cTribMun é código complementar da PREFEITURA (até 3 dígitos),
validado no cadastro SEFIN/ADN — NÃO derivar de LC 116 (01.07 → 107 falha E0314).
Preencher só via regra fiscal explícita (CSV/contador) após simulação no Portal Nacional.
"""

from __future__ import annotations

ATIBAIA_IBGE = "3504107"

# Referência lab/descontinuado — não usar em resolve_c_trib_mun automático.
LC116_TO_CTRIB_MUN: dict[str, str] = {}


def resolve_c_trib_mun(
    *,
    ibge_code: str,
    service_code: str,
    rule_c_trib_mun: str = "",
) -> str:
    """Resolve cTribMun para DPS — apenas valor explícito na regra municipal."""
    return (rule_c_trib_mun or "").strip()
