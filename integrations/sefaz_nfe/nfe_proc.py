"""Montagem nfeProc (NFe assinada + protNFe) — MOC NF-e v4.00."""

from __future__ import annotations

from lxml import etree

from integrations.nfse.xml_safe import safe_fromstring

NFE_NS = "http://www.portalfiscal.inf.br/nfe"


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def extract_prot_nfe_xml(sefaz_body: str | bytes | None) -> bytes | None:
    """Extrai o primeiro elemento protNFe da resposta SOAP/retEnviNFe."""
    if not sefaz_body:
        return None
    text = (
        sefaz_body.decode("utf-8", errors="replace")
        if isinstance(sefaz_body, (bytes, bytearray))
        else str(sefaz_body)
    )
    if not text.strip():
        return None
    root = safe_fromstring(text.encode("utf-8"))
    for el in root.iter():
        if _local(el.tag) == "protNFe":
            return etree.tostring(el, encoding="UTF-8", xml_declaration=False)
    return None


def build_synthetic_prot_nfe(
    *,
    access_key: str,
    protocol: str,
    tp_amb: str = "2",
    dh_recbto: str = "",
    c_stat: str = "100",
    x_motivo: str = "Autorizado o uso da NF-e",
) -> bytes:
    """protNFe sintético (stub/lab) quando SEFAZ não retorna XML completo."""
    ch = "".join(c for c in str(access_key or "") if c.isdigit())[:44]
    prot = etree.Element(f"{{{NFE_NS}}}protNFe", nsmap={None: NFE_NS}, versao="4.00")
    inf = etree.SubElement(prot, f"{{{NFE_NS}}}infProt")
    etree.SubElement(inf, f"{{{NFE_NS}}}tpAmb").text = str(tp_amb or "2")[:1]
    if ch:
        etree.SubElement(inf, f"{{{NFE_NS}}}verAplic").text = "EXEQ-HUB"
        etree.SubElement(inf, f"{{{NFE_NS}}}chNFe").text = ch
    if dh_recbto:
        etree.SubElement(inf, f"{{{NFE_NS}}}dhRecbto").text = dh_recbto
    if protocol:
        etree.SubElement(inf, f"{{{NFE_NS}}}nProt").text = str(protocol)[:15]
    etree.SubElement(inf, f"{{{NFE_NS}}}cStat").text = str(c_stat or "100")[:3]
    etree.SubElement(inf, f"{{{NFE_NS}}}xMotivo").text = (x_motivo or "")[:255]
    return etree.tostring(prot, encoding="UTF-8", xml_declaration=False)


def wrap_nfe_proc(*, signed_nfe_xml: bytes, prot_nfe_xml: bytes) -> bytes:
    """Envolve NFe (com Signature) e protNFe em nfeProc versao 4.00."""
    nfe_root = safe_fromstring(signed_nfe_xml)
    if _local(nfe_root.tag) != "NFe":
        raise ValueError("signed_nfe_xml deve ter raiz NFe")

    prot_root = safe_fromstring(prot_nfe_xml)
    if _local(prot_root.tag) != "protNFe":
        raise ValueError("prot_nfe_xml deve ter raiz protNFe")

    proc = etree.Element(f"{{{NFE_NS}}}nfeProc", nsmap={None: NFE_NS}, versao="4.00")
    proc.append(nfe_root)
    proc.append(prot_root)
    return etree.tostring(proc, xml_declaration=True, encoding="UTF-8")


def authorized_xml_bytes(
    *,
    signed_nfe_xml: bytes | None,
    sefaz_body: str | bytes | None = None,
    access_key: str = "",
    protocol: str = "",
    tp_amb: str = "2",
    dh_recbto: str = "",
    c_stat: str = "100",
    x_motivo: str = "",
) -> bytes | None:
    """
    Preferência: nfeProc com protNFe da SEFAZ; senão protNFe sintético (stub).
    Retorna None se não houver NFe assinada.
    """
    if not signed_nfe_xml:
        return None
    prot = extract_prot_nfe_xml(sefaz_body)
    if prot is None and access_key and protocol:
        prot = build_synthetic_prot_nfe(
            access_key=access_key,
            protocol=protocol,
            tp_amb=tp_amb,
            dh_recbto=dh_recbto,
            c_stat=c_stat,
            x_motivo=x_motivo or "Autorizado o uso da NF-e",
        )
    if prot is None:
        return signed_nfe_xml
    return wrap_nfe_proc(signed_nfe_xml=signed_nfe_xml, prot_nfe_xml=prot)
