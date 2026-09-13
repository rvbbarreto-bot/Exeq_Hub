from decimal import Decimal

from integrations.nfse.trib_fields import (
    format_iss_rate_percent,
    resolve_op_simp_nac,
    resolve_p_aliq,
    should_emit_municipal_iss_rate,
)
from apps.master_data.models import TaxRegime


def test_op_simp_from_rule_params():
    assert resolve_op_simp_nac(params={"simples_codigo_tributacao": 2}, tax_regime=TaxRegime.SIMPLES) == 2
    assert resolve_op_simp_nac(params={}, tax_regime=TaxRegime.SIMPLES) == 3
    assert resolve_op_simp_nac(params={}, tax_regime=TaxRegime.PRESUMIDO) == 1


def test_should_emit_municipal_rate_sefin_e0625():
    assert should_emit_municipal_iss_rate(op_simp_nac=3, tipo_retencao=1) is False
    assert should_emit_municipal_iss_rate(op_simp_nac=3, tipo_retencao=2) is True
    assert should_emit_municipal_iss_rate(op_simp_nac=1, tipo_retencao=1) is True


def test_p_aliq_sn_retained():
    params = {"iss_rate": "0.0500", "iss_retained": True}
    assert resolve_p_aliq(params=params, op_simp_nac=3, tipo_retencao=2) == "5.00"


def test_p_aliq_sn_not_retained_absent():
    params = {"iss_rate": "0.0200", "iss_retained": False}
    assert resolve_p_aliq(params=params, op_simp_nac=3, tipo_retencao=1) is None


def test_format_iss_rate_percent():
    assert format_iss_rate_percent(Decimal("0.0200")) == "2.00"
