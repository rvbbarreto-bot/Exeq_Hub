"""RTC goods compartilhado NF-e/NFC-e."""

from __future__ import annotations

from datetime import date

import pytest

from apps.fiscal.rtc_classification import seed_minimal_rtc_pack
from apps.fiscal.rtc_goods import (
    RTC_2026_CBS_BP,
    build_item_rtc,
    compute_goods_rtc_block,
    nfe_rtc_mode,
    resolve_goods_classification,
)


def test_compute_goods_rtc_2026_rates():
    block = compute_goods_rtc_block(base_cents=10_000, issue_date=date(2026, 9, 4))
    assert block["p_cbs_bp"] == RTC_2026_CBS_BP
    assert block["v_cbs_cents"] == 90
    assert block["v_ibs_cents"] == 10


@pytest.mark.django_db
def test_resolve_goods_classification_with_seed():
    seed_minimal_rtc_pack()
    cls = resolve_goods_classification()
    assert cls["status"] == "ok"
    assert cls["cst"] == "000"


def test_nfe_rtc_shadow(settings):
    settings.NFE_RTC_MODE = "shadow"
    rtc = build_item_rtc(
        line_total_cents=10_000,
        issue_date=date(2026, 1, 1),
        document_model="55",
    )
    assert rtc["mode"] == "shadow"
    assert rtc["status"] == "shadow"
    assert rtc["xml_ub"] is False


@pytest.mark.django_db
def test_nfe_rtc_emit_requires_classification(settings):
    settings.NFE_RTC_MODE = "emit"
    rtc = build_item_rtc(
        line_total_cents=10_000,
        issue_date=date(2026, 1, 1),
        document_model="55",
    )
    assert rtc["status"] == "blocked"

    seed_minimal_rtc_pack()
    rtc2 = build_item_rtc(
        line_total_cents=10_000,
        issue_date=date(2026, 1, 1),
        document_model="55",
    )
    assert rtc2["mode"] == "emit"
    assert rtc2["xml_ub"] is True
    assert rtc2["classification"]["status"] == "ok"


def test_nfe_rtc_mode_invalid_defaults_shadow(settings):
    settings.NFE_RTC_MODE = "invalid"
    assert nfe_rtc_mode() == "shadow"
