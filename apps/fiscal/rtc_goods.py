"""RTC IBS/CBS — mercadorias NF-e 55 / NFC-e 65 (ano-teste 2026)."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.conf import settings

from apps.fiscal.rtc_classification import resolve_rtc_classification

RTC_2026_CBS_BP = 90  # 0,9%
RTC_2026_IBS_BP = 10  # 0,1%
RTC_DEFAULT_CST = "000"
RTC_DEFAULT_CLASS = "000001"
RTC_DEFAULT_IND_OP = "100301"


def _normalize_mode(raw: str) -> str:
    mode = (raw or "shadow").strip().lower()
    if mode not in {"off", "shadow", "emit"}:
        return "shadow"
    return mode


def nfe_rtc_mode() -> str:
    return _normalize_mode(getattr(settings, "NFE_RTC_MODE", "shadow"))


def nfce_rtc_mode() -> str:
    return _normalize_mode(getattr(settings, "NFCE_RTC_MODE", "shadow"))


def goods_rtc_mode(*, document_model: str = "65") -> str:
    if str(document_model) == "55":
        return nfe_rtc_mode()
    return nfce_rtc_mode()


def rtc_active_for_date(issue_date: date | str | None) -> bool:
    if issue_date is None:
        return True
    if isinstance(issue_date, str):
        try:
            issue_date = date.fromisoformat(issue_date[:10])
        except ValueError:
            return True
    return issue_date.year >= 2026


def resolve_goods_classification() -> dict[str, Any]:
    """Resolve CST/cClassTrib/cIndOp; fallback seed quando sem versão publicada."""
    try:
        return resolve_rtc_classification(
            cst=RTC_DEFAULT_CST,
            c_class_trib=RTC_DEFAULT_CLASS,
            c_ind_op=RTC_DEFAULT_IND_OP,
        )
    except Exception:
        return {
            "status": "unresolved",
            "reason": "classification_error",
            "cst": RTC_DEFAULT_CST,
            "c_class_trib": RTC_DEFAULT_CLASS,
            "c_ind_op": RTC_DEFAULT_IND_OP,
            "requires_group": "gIBSCBS",
        }


def _money_from_cents(cents: int) -> str:
    return f"{Decimal(int(cents)) / Decimal(100):.2f}"


def _rate_str(bp: int) -> str:
    return f"{Decimal(bp) / Decimal(100):.4f}"


def compute_goods_rtc_block(
    *,
    base_cents: int,
    issue_date: date | str | None = None,
    classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    cls = classification or resolve_goods_classification()
    return {
        "status": "computed",
        "period": "2026_test",
        "cst": cls.get("cst") or RTC_DEFAULT_CST,
        "c_class_trib": cls.get("c_class_trib") or RTC_DEFAULT_CLASS,
        "c_ind_op": cls.get("c_ind_op") or RTC_DEFAULT_IND_OP,
        "classification": cls,
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
    document_model: str = "65",
) -> dict[str, Any]:
    mode = goods_rtc_mode(document_model=document_model)
    if mode == "off" or not rtc_active_for_date(issue_date):
        return {"status": "off", "mode": mode}
    cls = resolve_goods_classification()
    if mode == "emit" and cls.get("status") != "ok":
        return {
            "status": "blocked",
            "mode": mode,
            "reason": cls.get("reason") or "rtc_classification_unresolved",
            "classification": cls,
        }
    block = compute_goods_rtc_block(
        base_cents=line_total_cents,
        issue_date=issue_date,
        classification=cls,
    )
    block["mode"] = mode
    block["document_model"] = str(document_model)
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
    return {
        "v_bc": _money_from_cents(int(block.get("base_cents") or 0)),
        "p_ibs_uf": _rate_str(int(block.get("p_ibs_bp") or RTC_2026_IBS_BP)),
        "v_ibs_uf": _money_from_cents(
            int(block.get("v_ibs_uf_cents") or block.get("v_ibs_cents") or 0)
        ),
        "v_ibs": _money_from_cents(int(block.get("v_ibs_cents") or 0)),
        "p_cbs": _rate_str(int(block.get("p_cbs_bp") or RTC_2026_CBS_BP)),
        "v_cbs": _money_from_cents(int(block.get("v_cbs_cents") or 0)),
    }


def rtc_emit_xml_active(*, totals: dict[str, Any], mode: str) -> bool:
    if mode != "emit":
        return False
    rtc = totals.get("rtc") if isinstance(totals.get("rtc"), dict) else {}
    return bool(int(rtc.get("v_ibs_cents") or 0) + int(rtc.get("v_cbs_cents") or 0))


def effective_payable_cents(totals: dict[str, Any], *, mode: str) -> int:
    """vPag = vNFTot quando RTC emit; senão vNF."""
    base = int(totals.get("total_cents") or 0)
    if not rtc_emit_xml_active(totals=totals, mode=mode):
        return base
    rtc = totals.get("rtc") if isinstance(totals.get("rtc"), dict) else {}
    return int(rtc.get("v_nftot_cents") or base)


def resolve_cmun_fg_ibs(snapshot: dict[str, Any]) -> str:
    """Município fato gerador IBS/CBS — destino preferido, senão emitente."""
    dest = snapshot.get("destinatario") or {}
    ident = snapshot.get("identification") or {}
    emit = snapshot.get("emitente") or {}

    def _ibge(addr: dict) -> str:
        raw = addr.get("codigo_ibge") or addr.get("ibge") or addr.get("cMun") or ""
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        return digits[:7] if len(digits) >= 7 else ""

    dest_addr = dest.get("address") or ident.get("address") or {}
    emit_addr = emit.get("address") or {}
    return _ibge(dest_addr) or _ibge(emit_addr)


def build_goods_rtc_forensic(
    *,
    rtc_totals: dict[str, Any],
    catalog_meta: dict[str, Any],
    mode: str,
    document_model: str,
    layout: str = "",
) -> dict[str, Any]:
    from apps.fiscal.rtc_forensic import build_forensic_snapshot

    return build_forensic_snapshot(
        iss_payload={"document_model": document_model},
        rtc_block={
            "status": "computed" if mode in {"shadow", "emit"} else "off",
            "mode": mode,
            "totals": rtc_totals,
            "document_model": document_model,
        },
        national_catalog=catalog_meta,
        layout=layout,
    )
