"""Compat — use apps.fiscal.rtc_goods."""

from apps.fiscal.rtc_goods import (  # noqa: F401
    RTC_2026_CBS_BP,
    RTC_2026_IBS_BP,
    RTC_DEFAULT_CLASS,
    RTC_DEFAULT_CST,
    RTC_DEFAULT_IND_OP,
    aggregate_rtc_totals,
    build_item_rtc,
    compute_goods_rtc_block,
    nfce_rtc_mode,
    rtc_active_for_date,
    rtc_money_fields,
)
