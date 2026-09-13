"""Interpretação de cStat no XML NFS-e Nacional (consulta SEFIN)."""

from __future__ import annotations

from lxml import etree


def cstat_from_nfse_xml(xml_bytes: bytes | None) -> str:
    if not xml_bytes:
        return ""
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return ""
    for el in root.iter():
        if etree.QName(el).localname.lower() == "cstat" and (el.text or "").strip():
            return str(el.text).strip()
    return ""


def status_from_sefin_cstat(cstat: str) -> str | None:
    code = (cstat or "").strip().upper()
    if code in {"101", "CANCELADA"}:
        return "cancelled"
    if code in {"100", "AUTORIZADA"}:
        return "authorized"
    return None


def event_response_indicates_cancelled(
    *,
    status_code: int,
    data: dict | None = None,
    xml_bytes: bytes | None = None,
) -> bool:
    if status_code == 404:
        return False
    if status_code not in {200, 201}:
        return False
    payload = data or {}
    cstat = str(payload.get("cStat") or payload.get("cstat") or "").strip()
    if cstat in {"101", "135"}:
        return True
    text = (xml_bytes or b"").decode("utf-8", errors="replace").lower()
    return "e101101" in text


def resolve_status_from_nfse_payload(
    *,
    xml_bytes: bytes | None,
    data: dict | None = None,
) -> str | None:
    from_data = status_from_sefin_cstat(
        str((data or {}).get("cStat") or (data or {}).get("cstat") or "")
    )
    if from_data:
        return from_data
    return status_from_sefin_cstat(cstat_from_nfse_xml(xml_bytes))
