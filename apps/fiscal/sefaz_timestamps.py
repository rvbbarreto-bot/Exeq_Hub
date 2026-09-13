"""Persistência de dhEmi/dhRecbto no fiscal_snapshot (NF-e e NFC-e)."""

from __future__ import annotations

from typing import Any

from integrations.sefaz_nfe.fiscal_time import format_fiscal_iso, fiscal_local_now


def stamp_dh_emi(snapshot: dict[str, Any]) -> dict[str, Any]:
    out = dict(snapshot)
    header = dict(out.get("header") or {})
    header["dh_emi"] = format_fiscal_iso(fiscal_local_now())
    out["header"] = header
    return out


def authorization_dh_recbto(result: Any) -> str:
    raw = result.raw if isinstance(getattr(result, "raw", None), dict) else {}
    dh = str(raw.get("dhRecbto") or "").strip()
    if dh:
        return dh
    return format_fiscal_iso(fiscal_local_now())


def persist_authorization_meta(invoice: Any, result: Any) -> None:
    snap = dict(invoice.fiscal_snapshot or {})
    sefaz_meta = dict(snap.get("sefaz") or {}) if isinstance(snap.get("sefaz"), dict) else {}
    sefaz_meta["dh_recbto"] = authorization_dh_recbto(result)
    snap["sefaz"] = sefaz_meta
    invoice.fiscal_snapshot = snap
