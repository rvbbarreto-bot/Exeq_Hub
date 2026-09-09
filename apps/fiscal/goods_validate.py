"""Validação mercadorias — flag unificado, perfil fiscal e GTIN (ADR-GOODS-VALIDATE-V1)."""

from __future__ import annotations

from typing import Literal

from django.conf import settings

from apps.fiscal.cross_validate_rules import ST_CFOPS

CrossValidateContext = Literal["catalog", "draft", "emit"]

FISCAL_PROFILE_SIMPLE_RETAIL = "simple_retail"
FISCAL_PROFILE_RETAIL_ST = "retail_st"

ST_CSOSN = frozenset({"500"})


def goods_cross_validate_setting() -> str:
    g = getattr(settings, "GOODS_CROSS_VALIDATE", None)
    n = getattr(settings, "NFE_CROSS_VALIDATE", None)
    raw = g if g not in (None, "") else n
    mode = (raw or "warn").strip().lower()
    if mode not in {"off", "warn", "block"}:
        return "warn"
    return mode


def effective_cross_validate_mode(
    *,
    context: CrossValidateContext = "draft",
    http_emit: bool = False,
) -> str:
    """
    P3: warn no cadastro; block no emit HTTP produção.
    """
    base = goods_cross_validate_setting()
    if base == "off":
        return "off"
    if context == "catalog":
        return "warn"
    if context == "emit" and http_emit:
        return "block"
    return base


def tenant_fiscal_profile(tenant) -> str:
    if tenant is None:
        return FISCAL_PROFILE_SIMPLE_RETAIL
    settings_map = getattr(tenant, "settings", None) or {}
    if not isinstance(settings_map, dict):
        return FISCAL_PROFILE_SIMPLE_RETAIL
    profile = (settings_map.get("fiscal_profile") or FISCAL_PROFILE_SIMPLE_RETAIL).strip()
    return profile or FISCAL_PROFILE_SIMPLE_RETAIL


def validate_fiscal_profile_product(
    *,
    fiscal_profile: str,
    cfop_internal: str = "",
    cfop_interstate: str = "",
    csosn: str = "",
) -> list[dict[str, str]]:
    """P1: simple_retail bloqueia ST no catálogo."""
    if fiscal_profile != FISCAL_PROFILE_SIMPLE_RETAIL:
        return []
    errors: list[dict[str, str]] = []
    csosn_val = (csosn or "").strip()
    if csosn_val in ST_CSOSN:
        errors.append(
            {
                "rule": "RULE-PROFILE-ST",
                "field": "csosn",
                "message": "Perfil simple_retail (v1 ALE) não permite CSOSN 500 (ST)",
            }
        )
    for label, cfop, field in (
        ("interno", cfop_internal, "cfop_internal"),
        ("interestadual", cfop_interstate, "cfop_interstate"),
    ):
        code = "".join(ch for ch in str(cfop or "") if ch.isdigit())
        if code in ST_CFOPS:
            errors.append(
                {
                    "rule": "RULE-PROFILE-ST",
                    "field": field,
                    "message": f"Perfil simple_retail (v1 ALE) não permite CFOP ST {code} ({label})",
                }
            )
    return errors


def validate_fiscal_profile_item(
    *,
    fiscal_profile: str,
    cfop: str = "",
    csosn: str = "",
    line_number: int = 0,
) -> list[dict[str, str]]:
    if fiscal_profile != FISCAL_PROFILE_SIMPLE_RETAIL:
        return []
    prefix = f"items[{line_number}]." if line_number else "items[]."
    errors: list[dict[str, str]] = []
    csosn_val = (csosn or "").strip()
    if csosn_val in ST_CSOSN:
        errors.append(
            {
                "rule": "RULE-PROFILE-ST",
                "field": f"{prefix}csosn",
                "message": "Perfil simple_retail (v1 ALE) não permite CSOSN 500 (ST)",
            }
        )
    code = "".join(ch for ch in str(cfop or "") if ch.isdigit())
    if code in ST_CFOPS:
        errors.append(
            {
                "rule": "RULE-PROFILE-ST",
                "field": f"{prefix}cfop",
                "message": f"Perfil simple_retail (v1 ALE) não permite CFOP ST {code}",
            }
        )
    return errors


def normalize_gtin(raw: str | None) -> str:
    """P2: vazio → ''; serialização XML usa resolve_c_ean."""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text or text.upper() in {"SEM GTIN", "SEM_GTIN", "NONE"}:
        return ""
    return "".join(ch for ch in text if ch.isdigit())[:14]


def resolve_c_ean(gtin: str | None) -> str:
    """Tag cEAN / cEANTrib — Sefaz exige valor ou 'SEM GTIN'."""
    digits = normalize_gtin(gtin)
    if not digits:
        return "SEM GTIN"
    if len(digits) not in {8, 12, 13, 14}:
        return "SEM GTIN"
    return digits
