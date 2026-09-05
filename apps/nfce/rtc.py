"""RTC IBS/CBS — mercadoria NFC-e mod 65 (ano-teste 2026)."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.conf import settings

# NT 2025.002 — ano-teste 2026 (destaque informativo)
RTC_2026_CBS_BP = 90  # 0,9%
RTC_2026_IBS_BP = 10  # 0,1%
RTC_DEFAULT_CST = "000"
RTC_DEFAULT_CLASS = "000001"
RTC_DEFAULT_IND_OP = "100301"


def nfce_rtc_mode() -> str:
    mode = (getattr(settings, "NFCE_RTC_MODE", "shadow") or "shadow").strip().lower()
    if mode not in {"off", "shadow", "emit"}:
        return "shadow"
    return mode


def rtc_active_for_date(issue_date: date | str | None) -> bool:
    if issue_date is None:
        return True
    if isinstance(issue_date, str):
        try:
            issue_date = date.fromisoformat(issue_date[:10])
        except ValueError:
            return True
    return issue_date.year >= 2026


def _money_from_cents(cents: int) -> str:
    return f"{Decimal(int(cents)) / Decimal(100):.2f}"


def _rate_str(bp: int) -> str:
    return f"{Decimal(bp) / Decimal(100):.4f}"


def compute_goods_rtc_block(*, base_cents: int, issue_date: date | str | None = None) -> dict[str, Any]:
    """Calcula IBS/CBS informativos sobre vBC = total item/NF."""
    base = max(int(base_cents or 0), 0)
    v_cbs_cents = int(
        (Decimal(base) * Decimal(RTC_2026_CBS_BP) / Decimal(10000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    v_ibs_cents = int(
        (Decimal(base) * Decimal(RTC_2026_IBS_BP) / Decimal(10000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    return {
        "status": "computed",
        "period": "2026_test",
        "cst": RTC_DEFAULT_CST,
        "c_class_trib": RTC_DEFAULT_CLASS,
        "c_ind_op": RTC_DEFAULT_IND_OP,
        "base_cents": base,
        "p_cbs_bp": RTC_2026_CBS_BP,
        "p_ibs_bp": RTC_2026_IBS_BP,
        "v_cbs_cents": v_cbs_cents,
        "v_ibs_cents": v_ibs_cents,
        "v_ibs_uf_cents": v_ibs_cents,
        "v_ibs_mun_cents": 0,
        "active_for_date": rtc_active_for_date(issue_date),
    }


def build_item_rtc(
    *,
    line_total_cents: int,
    issue_date: date | str | None,
) -> dict[str, Any]:
    mode = nfce_rtc_mode()
    if mode == "off" or not rtc_active_for_date(issue_date):
        return {"status": "off", "mode": mode}
    block = compute_goods_rtc_block(base_cents=line_total_cents, issue_date=issue_date)
    block["mode"] = mode
    block["xml_ub"] = mode == "emit"
    if mode == "shadow":
        block["status"] = "shadow"
    return block


def aggregate_rtc_totals(items_taxes: list[dict[str, Any]]) -> dict[str, Any]:
    base = 0
    v_ibs = 0
    v_cbs = 0
    for row in items_taxes:
        rtc = (row.get("taxes") or {}).get("rtc") or {}
        if rtc.get("status") in {"computed", "shadow"} or rtc.get("mode") == "emit":
            base += int(rtc.get("base_cents") or row.get("total_cents") or 0)
            v_ibs += int(rtc.get("v_ibs_cents") or 0)
            v_cbs += int(rtc.get("v_cbs_cents") or 0)
    return {
        "base_cents": base,
        "v_ibs_cents": v_ibs,
        "v_cbs_cents": v_cbs,
        "v_nftot_cents": base + v_ibs + v_cbs,
    }


def rtc_money_fields(block: dict[str, Any]) -> dict[str, str]:
    """Campos formatados para XML."""
    return {
        "v_bc": _money_from_cents(int(block.get("base_cents") or 0)),
        "p_ibs_uf": _rate_str(int(block.get("p_ibs_bp") or RTC_2026_IBS_BP)),
        "v_ibs_uf": _money_from_cents(int(block.get("v_ibs_uf_cents") or block.get("v_ibs_cents") or 0)),
        "v_ibs": _money_from_cents(int(block.get("v_ibs_cents") or 0)),
        "p_cbs": _rate_str(int(block.get("p_cbs_bp") or RTC_2026_CBS_BP)),
        "v_cbs": _money_from_cents(int(block.get("v_cbs_cents") or 0)),
    }
