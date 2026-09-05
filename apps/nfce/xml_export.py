"""Exportação XML NFC-e — reinjeta CSC para QR na reconstrução."""

from __future__ import annotations

from apps.nfce.models import NfceInvoice


def _snap_with_csc(invoice: NfceInvoice) -> dict | None:
    snap = invoice.fiscal_snapshot
    if not isinstance(snap, dict) or not snap.get("items"):
        return None
    out = dict(snap)
    from apps.nfce.csc import resolve_csc

    csc_id, csc_token = resolve_csc(
        tenant=invoice.tenant, provider=invoice.provider, tp_amb=invoice.tp_amb
    )
    sefaz = dict(out.get("sefaz") or {})
    sefaz["csc_id"] = csc_id
    sefaz["csc_token"] = csc_token
    out["sefaz"] = sefaz
    header = dict(out.get("header") or {})
    header["csc_id"] = csc_id
    header["csc_token"] = csc_token
    out["header"] = header
    return out


def resolve_authorized_xml_bytes(invoice: NfceInvoice) -> bytes | None:
    if invoice.status != NfceInvoice.Status.AUTHORIZED:
        return None
    snap = _snap_with_csc(invoice)
    if not snap:
        return None
    key = "".join(ch for ch in str(invoice.access_key or "") if ch.isdigit())[:44]
    if len(key) != 44:
        return None
    from integrations.sefaz_nfe.xml_nfce import build_nfce_xml

    return build_nfce_xml(snapshot=snap, access_key=key)
