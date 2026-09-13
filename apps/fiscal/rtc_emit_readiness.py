"""Gate RTC emit (homolog/prod) — NF-e 55 / NFC-e 65."""

from __future__ import annotations

from datetime import date
from typing import Any

from django.conf import settings

from apps.fiscal.rtc_classification import get_published_rtc_version
from apps.fiscal.rtc_goods import (
    goods_rtc_mode,
    resolve_goods_classification,
    rtc_active_for_date,
)


def assess_rtc_emit_readiness(
    *,
    document_model: str = "55",
    issue_date: date | str | None = None,
) -> dict[str, Any]:
    mode = goods_rtc_mode(document_model=document_model)
    if mode != "emit":
        return {"ok": True, "mode": mode, "blockers": [], "warnings": []}

    blockers: list[str] = []
    warnings: list[str] = []

    if not rtc_active_for_date(issue_date):
        blockers.append("issue_date_before_rtc_2026")

    cls = resolve_goods_classification()
    if cls.get("status") != "ok":
        blockers.append("rtc_classification_unpublished")

    if get_published_rtc_version() is None:
        blockers.append("no_published_rtc_normative_version")

    layout = (
        getattr(settings, "NFE_LAYOUT_VERSION", "")
        if document_model == "55"
        else getattr(settings, "NFCE_LAYOUT_VERSION", "")
    )
    if not layout or "stub" in layout.lower():
        warnings.append("layout_version_stub_homolog_pin_recommended")

    http_mode = (
        getattr(settings, "NFE_HTTP_MODE", "stub")
        if document_model == "55"
        else getattr(settings, "NFCE_HTTP_MODE", "stub")
    )
    if (http_mode or "stub").lower() == "stub":
        warnings.append("http_mode_stub_rtc_emit_xml_only")

    return {
        "ok": not blockers,
        "mode": mode,
        "blockers": blockers,
        "warnings": warnings,
        "classification": cls,
        "layout_version": layout,
        "http_mode": http_mode,
    }
