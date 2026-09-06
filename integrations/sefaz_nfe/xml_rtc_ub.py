"""Grupo UB (IBSCBS) — RTC emit NF-e/NFC-e (NT 2025.002)."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from apps.fiscal.rtc_goods import RTC_DEFAULT_CLASS, RTC_DEFAULT_CST, rtc_money_fields
from integrations.sefaz_nfe.xml_nfe import _el


def append_item_ibscbs(imposto: ET.Element, rtc: dict[str, Any]) -> None:
    if not rtc or not rtc.get("xml_ub"):
        return
    money = rtc_money_fields(rtc)
    ibscbs = _el(imposto, "IBSCBS")
    _el(ibscbs, "CST", str(rtc.get("cst") or RTC_DEFAULT_CST)[:3])
    _el(ibscbs, "cClassTrib", str(rtc.get("c_class_trib") or RTC_DEFAULT_CLASS)[:6])
    grp = _el(ibscbs, "gIBSCBS")
    _el(grp, "vBC", money["v_bc"])
    ibsuf = _el(grp, "gIBSUF")
    _el(ibsuf, "pIBSUF", money["p_ibs_uf"])
    _el(ibsuf, "vIBSUF", money["v_ibs_uf"])
    _el(grp, "vIBS", money["v_ibs"])
    cbs = _el(grp, "gCBS")
    _el(cbs, "pCBS", money["p_cbs"])
    _el(cbs, "vCBS", money["v_cbs"])


def append_total_ibscbs(
    total_el: ET.Element, rtc_totals: dict[str, Any], *, v_nf_cents: int
) -> int:
    """Grupo W03 — retorna vNFTot em centavos."""
    if not rtc_totals or int(rtc_totals.get("v_ibs_cents") or 0) + int(
        rtc_totals.get("v_cbs_cents") or 0
    ) <= 0:
        return v_nf_cents
    money = rtc_money_fields(
        {
            "base_cents": rtc_totals.get("base_cents"),
            "v_ibs_cents": rtc_totals.get("v_ibs_cents"),
            "v_cbs_cents": rtc_totals.get("v_cbs_cents"),
            "v_ibs_uf_cents": rtc_totals.get("v_ibs_cents"),
            "p_ibs_bp": 10,
            "p_cbs_bp": 90,
        }
    )
    ibs_tot = _el(total_el, "IBSCBSTot")
    _el(ibs_tot, "vBCIBSCBS", money["v_bc"])
    _el(ibs_tot, "vIBS", money["v_ibs"])
    _el(ibs_tot, "vCBS", money["v_cbs"])
    v_nftot = int(
        rtc_totals.get("v_nftot_cents")
        or (
            v_nf_cents
            + int(rtc_totals.get("v_ibs_cents") or 0)
            + int(rtc_totals.get("v_cbs_cents") or 0)
        )
    )
    _el(ibs_tot, "vNFTot", f"{v_nftot / 100:.2f}")
    return v_nftot
