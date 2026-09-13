"""CSC + QR Code NFC-e v2 (infNFeSupl) — emissão online SP."""

from __future__ import annotations

import hashlib
from xml.etree import ElementTree as ET

from integrations.sefaz_nfe.xml_nfe import _el


def qr_hash_online_v2(
    *,
    access_key: str,
    tp_amb: str,
    csc_id: str,
    csc_token: str,
) -> str:
    """
    Hash QR Code v2 emissão ONLINE (NT DANFE NFC-e).
    SHA1( chave|2|tpAmb|idCSC + CSC ) → hex 40 chars.
    """
    key = "".join(ch for ch in str(access_key) if ch.isdigit())[:44]
    amb = "2" if str(tp_amb) == "2" else "1"
    cid = str(int("".join(ch for ch in str(csc_id) if ch.isdigit()) or "1"))
    payload = f"{key}|2|{amb}|{cid}{csc_token}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest().upper()


def build_qr_code_url(
    *,
    access_key: str,
    tp_amb: str,
    csc_id: str = "1",
    csc_token: str = "",
    qr_base_url: str | None = None,
) -> str:
    key = "".join(ch for ch in str(access_key) if ch.isdigit())[:44]
    amb = "2" if str(tp_amb) == "2" else "1"
    cid = str(int("".join(ch for ch in str(csc_id) if ch.isdigit()) or "1"))
    digest = qr_hash_online_v2(
        access_key=key, tp_amb=amb, csc_id=cid, csc_token=csc_token
    )
    if not qr_base_url:
        qr_base_url = (
            "https://www.homologacao.nfce.fazenda.sp.gov.br/"
            "NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx"
            if amb == "2"
            else "https://www.nfce.fazenda.sp.gov.br/NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx"
        )
    return f"{qr_base_url}?p={key}|2|{amb}|{cid}|{digest}"


def append_nfce_supplement(
    nfe_root: ET.Element,
    *,
    access_key: str,
    tp_amb: str,
    total_cents: int,
    csc_id: str = "1",
    csc_token: str = "",
    qr_base_url: str | None = None,
) -> None:
    del total_cents  # reservado para QR offline (contingência)
    qr_url = build_qr_code_url(
        access_key=access_key,
        tp_amb=tp_amb,
        csc_id=csc_id,
        csc_token=csc_token,
        qr_base_url=qr_base_url,
    )
    supl = _el(nfe_root, "infNFeSupl")
    _el(supl, "qrCode", qr_url)
    base = qr_base_url or qr_url.split("?")[0]
    _el(supl, "urlChave", base)
