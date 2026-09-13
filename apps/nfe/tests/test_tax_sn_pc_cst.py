"""CST PIS/COFINS — Simples Nacional."""

from __future__ import annotations

from apps.nfe.tax import TaxRegime, calculate_item_taxes


def test_sn_coerces_regime_normal_pis_cofins_to_49():
    taxes = calculate_item_taxes(
        tax_regime=TaxRegime.SIMPLES,
        item_total_cents=10000,
        icms_rate_bp=0,
        csosn="102",
        icms_cst="",
        origin="0",
        pis_cst="01",
        pis_rate_bp=165,
        cofins_cst="02",
        cofins_rate_bp=760,
        emit_uf="SP",
        dest_uf="SP",
    )
    assert taxes["pis"]["cst"] == "49"
    assert taxes["cofins"]["cst"] == "49"
    assert taxes["pis"]["value_cents"] == 0
    assert taxes["cofins"]["value_cents"] == 0


def test_sn_defaults_pis_cofins_49():
    taxes = calculate_item_taxes(
        tax_regime=TaxRegime.SIMPLES,
        item_total_cents=5000,
        icms_rate_bp=0,
        csosn="102",
        icms_cst="",
        origin="0",
        pis_cst="",
        pis_rate_bp=0,
        cofins_cst="",
        cofins_rate_bp=0,
    )
    assert taxes["pis"]["cst"] == "49"
    assert taxes["cofins"]["cst"] == "49"
