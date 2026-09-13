"""RTC NFC-e — cálculo ano-teste 2026."""

from __future__ import annotations

from datetime import date

import pytest

from apps.nfce.rtc import (
    RTC_2026_CBS_BP,
    RTC_2026_IBS_BP,
    aggregate_rtc_totals,
    build_item_rtc,
    compute_goods_rtc_block,
    nfce_rtc_mode,
)


def test_compute_goods_rtc_2026_rates():
    block = compute_goods_rtc_block(base_cents=10_000, issue_date=date(2026, 9, 4))
    assert block["p_cbs_bp"] == RTC_2026_CBS_BP
    assert block["p_ibs_bp"] == RTC_2026_IBS_BP
    assert block["v_cbs_cents"] == 90
    assert block["v_ibs_cents"] == 10


def test_build_item_rtc_off(settings):
    settings.NFCE_RTC_MODE = "off"
    rtc = build_item_rtc(line_total_cents=5000, issue_date=date(2026, 1, 1))
    assert rtc["status"] == "off"


def test_build_item_rtc_shadow(settings):
    settings.NFCE_RTC_MODE = "shadow"
    rtc = build_item_rtc(line_total_cents=10_000, issue_date=date(2026, 1, 1))
    assert rtc["mode"] == "shadow"
    assert rtc["status"] == "shadow"
    assert rtc["xml_ub"] is False
    assert rtc["v_cbs_cents"] == 90


@pytest.mark.django_db
def test_build_item_rtc_emit_xml_flag(settings):
    from apps.fiscal.rtc_classification import seed_minimal_rtc_pack

    settings.NFCE_RTC_MODE = "emit"
    seed_minimal_rtc_pack()
    rtc = build_item_rtc(line_total_cents=10_000, issue_date=date(2026, 1, 1))
    assert rtc["mode"] == "emit"
    assert rtc["xml_ub"] is True


def test_aggregate_rtc_totals():
    items = [
        {
            "total_cents": 10_000,
            "taxes": {
                "rtc": {
                    "status": "shadow",
                    "base_cents": 10_000,
                    "v_ibs_cents": 10,
                    "v_cbs_cents": 90,
                }
            },
        },
        {
            "total_cents": 5_000,
            "taxes": {
                "rtc": {
                    "status": "shadow",
                    "base_cents": 5_000,
                    "v_ibs_cents": 5,
                    "v_cbs_cents": 45,
                }
            },
        },
    ]
    tot = aggregate_rtc_totals(items)
    assert tot["base_cents"] == 15_000
    assert tot["v_ibs_cents"] == 15
    assert tot["v_cbs_cents"] == 135
    assert tot["v_nftot_cents"] == 15_150


def test_nfce_rtc_mode_invalid_defaults_shadow(settings):
    settings.NFCE_RTC_MODE = "invalid"
    assert nfce_rtc_mode() == "shadow"
