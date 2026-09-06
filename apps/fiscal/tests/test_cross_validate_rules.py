"""Testes L5–L8 regras cruzadas."""

from __future__ import annotations

from datetime import date

from apps.fiscal.cross_validate_rules import (
    run_layers_l5_l8,
    validate_ipi_zero,
    validate_l5_ncm_cfop,
    validate_l6_ncm_pis_cst,
    validate_l7_st_cest,
    validate_l8_rtc_crt3,
)


def test_l5_beverage_cfop_conflict():
    err = validate_l5_ncm_cfop(ncm="22021000", cfop="5101")
    assert err is not None
    assert err["rule"] == "RULE-L5-NCM-CFOP"


def test_l5_ok_revenda():
    assert validate_l5_ncm_cfop(ncm="22021000", cfop="5102") is None


def test_l6_monofasic_requires_cst04():
    err = validate_l6_ncm_pis_cst(ncm="22021000", pis_cst="07", cofins_cst="07")
    assert err is not None
    ok = validate_l6_ncm_pis_cst(ncm="22021000", pis_cst="04", cofins_cst="04")
    assert ok is None


def test_l7_st_requires_cest():
    err = validate_l7_st_cest(cfop="5405", cest="")
    assert err is not None
    assert validate_l7_st_cest(cfop="5405", cest="1234567") is None
    assert validate_l7_st_cest(cfop="5102", cest="") is None


def test_l8_rtc_crt3_after_cutoff():
    err = validate_l8_rtc_crt3(
        crt="3",
        issue_date=date(2026, 9, 1),
        rtc_mode="emit",
        classification_status="unresolved",
    )
    assert err is not None
    assert validate_l8_rtc_crt3(
        crt="3",
        issue_date=date(2026, 9, 1),
        rtc_mode="emit",
        classification_status="ok",
    ) is None


def test_ipi_zero_requires_cst_and_enq():
    assert validate_ipi_zero(ipi_rate_bp=0, ipi_cst="", ip_enq="") is None
    err = validate_ipi_zero(ipi_rate_bp=500, ipi_cst="", ip_enq="")
    assert err["rule"] == "RULE-IPI-0-CST"
    err2 = validate_ipi_zero(ipi_rate_bp=500, ipi_cst="50", ip_enq="")
    assert err2["rule"] == "RULE-IPI-0-ENQ"


def test_l8_rtc_before_cutoff_no_error():
    assert (
        validate_l8_rtc_crt3(
            crt="3",
            issue_date=date(2026, 1, 1),
            rtc_mode="emit",
            classification_status="unresolved",
        )
        is None
    )


def test_l8_shadow_mode_skips():
    assert validate_l8_rtc_crt3(crt="3", issue_date=date(2026, 9, 1), rtc_mode="shadow") is None


def test_l6_non_monofasic_skips():
    assert validate_l6_ncm_pis_cst(ncm="12345678", pis_cst="07", cofins_cst="07") is None


def test_run_layers_aggregates():
    errs = run_layers_l5_l8(
        ncm="22021000",
        cfop="5405",
        pis_cst="07",
        cofins_cst="07",
        cest="",
        ipi_rate_bp=100,
        ipi_cst="50",
        ip_enq="",
    )
    rules = {e["rule"] for e in errs}
    assert "RULE-L6-NCM-CST" in rules
    assert "RULE-L7-ST-CEST" in rules
    assert "RULE-IPI-0-ENQ" in rules
