"""Campos tributários compartilhados — DPS SEFIN e Focus nfsen."""

from __future__ import annotations

from decimal import Decimal

from apps.master_data.models import TaxRegime


def resolve_op_simp_nac(*, params: dict, tax_regime: str) -> int:
    """opSimpNac / codigo_opcao_simples_nacional a partir da regra fiscal."""
    raw = params.get("simples_codigo_tributacao")
    if raw is not None and str(raw).strip() != "":
        return int(raw)
    if tax_regime == TaxRegime.SIMPLES:
        return 3
    return 1


def resolve_iss_rate_decimal(params: dict) -> Decimal:
    return Decimal(str(params.get("iss_rate") or "0"))


def should_emit_municipal_iss_rate(*, op_simp_nac: int, tipo_retencao: int) -> bool:
    """
    SEFIN E0625 — ME/EPP (opSimpNac=3) sem retenção não informa alíquota municipal.
    """
    if int(tipo_retencao) != 1:
        return True
    return int(op_simp_nac) != 3


def format_iss_rate_percent(iss_rate: Decimal) -> str:
    """Converte fração (0.02) em percentual DPS/Focus (2.00)."""
    pct = (iss_rate * Decimal(100)).quantize(Decimal("0.01"))
    return f"{pct}"


def resolve_p_aliq(*, params: dict, op_simp_nac: int, tipo_retencao: int) -> str | None:
    if should_emit_municipal_iss_rate(
        op_simp_nac=op_simp_nac, tipo_retencao=tipo_retencao
    ):
        rate = resolve_iss_rate_decimal(params)
        if rate > 0:
            return format_iss_rate_percent(rate)
        return None
    override = params.get("percentual_aliquota_relativa_municipio")
    if override is not None and str(override).strip() != "":
        return format_iss_rate_percent(Decimal(str(override)) / Decimal(100))
    return None
