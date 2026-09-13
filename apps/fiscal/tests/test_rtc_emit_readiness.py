"""RTC emit readiness gate."""

from __future__ import annotations

import pytest

from apps.fiscal.rtc_classification import seed_minimal_rtc_pack
from apps.fiscal.rtc_emit_readiness import assess_rtc_emit_readiness
from apps.fiscal.rtc_goods import effective_payable_cents, resolve_cmun_fg_ibs


def test_effective_payable_shadow_uses_vnf():
    totals = {"total_cents": 10_000, "rtc": {"v_nftot_cents": 10_100}}
    assert effective_payable_cents(totals, mode="shadow") == 10_000


def test_effective_payable_emit_uses_vnftot():
    totals = {"total_cents": 10_000, "rtc": {"v_nftot_cents": 10_100, "v_ibs_cents": 10, "v_cbs_cents": 90}}
    assert effective_payable_cents(totals, mode="emit") == 10_100


def test_resolve_cmun_fg_ibs_prefers_dest():
    snap = {
        "emitente": {"address": {"codigo_ibge": "3504107"}},
        "destinatario": {"address": {"codigo_ibge": "3550308"}},
    }
    assert resolve_cmun_fg_ibs(snap) == "3550308"


@pytest.mark.django_db
def test_assess_rtc_emit_blocked_without_seed(settings):
    settings.NFE_RTC_MODE = "emit"
    result = assess_rtc_emit_readiness(document_model="55", issue_date="2026-09-04")
    assert result["ok"] is False
    assert "rtc_classification_unpublished" in result["blockers"]


@pytest.mark.django_db
def test_assess_rtc_emit_ok_after_seed(settings):
    settings.NFE_RTC_MODE = "emit"
    seed_minimal_rtc_pack()
    result = assess_rtc_emit_readiness(document_model="55", issue_date="2026-09-04")
    assert result["ok"] is True
