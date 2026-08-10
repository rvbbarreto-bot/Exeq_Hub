"""Assinatura XMLDSig da infNFe (reuso motor signxml do path NFS-e)."""

from __future__ import annotations

from lxml import etree

from integrations.nfse.xmldsig import SefinXmlDSigError, sign_referenced_element
from integrations.nfse.xml_safe import safe_fromstring


def sign_nfe_xml(*, nfe_xml: bytes | str, pfx_bytes: bytes, password: str = "") -> bytes:
    root = safe_fromstring(nfe_xml)
    local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if local != "NFe":
        raise SefinXmlDSigError("Raiz do XML deve ser NFe")
    inf = None
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "infNFe":
            inf = el
            break
    if inf is None:
        raise SefinXmlDSigError("infNFe não encontrado")
    return sign_referenced_element(
        root=root,
        target=inf,
        pfx_bytes=pfx_bytes,
        password=password,
    )


def wrap_envi_nfe(*, signed_nfe_xml: bytes, id_lote: str, ind_sinc: str = "1") -> bytes:
    """Envolve NFe assinada em enviNFe (envio síncrono preferencial)."""
    ns = "http://www.portalfiscal.inf.br/nfe"
    signed = safe_fromstring(signed_nfe_xml)
    envi = etree.Element(f"{{{ns}}}enviNFe", nsmap={None: ns}, versao="4.00")
    etree.SubElement(envi, f"{{{ns}}}idLote").text = str(id_lote)[:15]
    etree.SubElement(envi, f"{{{ns}}}indSinc").text = ind_sinc
    envi.append(signed)
    return etree.tostring(envi, xml_declaration=True, encoding="UTF-8")


def sign_evento_nfe_xml(*, env_evento_xml: bytes | str, pfx_bytes: bytes, password: str = "") -> bytes:
    """Assina `infEvento` (Id) dentro de envEvento/evento — cancel 110111 (I6)."""
    root = safe_fromstring(env_evento_xml)
    inf = None
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "infEvento":
            inf = el
            break
    if inf is None:
        raise SefinXmlDSigError("infEvento não encontrado")
    return sign_referenced_element(
        root=root,
        target=inf,
        pfx_bytes=pfx_bytes,
        password=password,
    )


def sign_inut_nfe_xml(*, inut_xml: bytes | str, pfx_bytes: bytes, password: str = "") -> bytes:
    """Assina `infInut` (Id) em inutNFe — inutilização (U15)."""
    root = safe_fromstring(inut_xml)
    inf = None
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "infInut":
            inf = el
            break
    if inf is None:
        raise SefinXmlDSigError("infInut não encontrado")
    return sign_referenced_element(
        root=root,
        target=inf,
        pfx_bytes=pfx_bytes,
        password=password,
    )
