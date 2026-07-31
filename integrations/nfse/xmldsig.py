"""XMLDSig Nacional — RSA-SHA1 enveloped (RF-13a / RF-31).

Manual SN NFS-e: C14N inclusivo 1.0, RSA-SHA1, enveloped, EndCertOnly,
Signature sem prefixo (E1228).

Usa signxml com `excise_empty_xmlns_declarations=True` (evita E0714).
"""

from __future__ import annotations

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)
from lxml import etree
from signxml import XMLSigner, methods

from integrations.nfse.xml_safe import safe_fromstring

NFSE_NS = "http://www.sped.fazenda.gov.br/nfse"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"
C14N_ALG = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"


class SefinXmlDSigError(RuntimeError):
    pass


class _XMLSignerSha1(XMLSigner):
    """SHA-1 ainda é o algoritmo exigido pelo SN NFS-e (manual)."""

    def check_deprecated_methods(self):
        return


def sign_dps_xml(*, dps_xml: bytes | str, pfx_bytes: bytes, password: str = "") -> bytes:
    root = safe_fromstring(dps_xml)
    if _local(root.tag) != "DPS":
        raise SefinXmlDSigError("Raiz do XML deve ser DPS")
    inf = root.find(f"{{{NFSE_NS}}}infDPS")
    if inf is None:
        inf = root.find("infDPS")
    if inf is None:
        raise SefinXmlDSigError("Elemento infDPS não encontrado")
    return sign_referenced_element(
        root=root,
        target=inf,
        pfx_bytes=pfx_bytes,
        password=password,
    )


def sign_ped_reg_evento_xml(
    *, evento_xml: bytes | str, pfx_bytes: bytes, password: str = ""
) -> bytes:
    root = safe_fromstring(evento_xml)
    if _local(root.tag) != "pedRegEvento":
        raise SefinXmlDSigError("Raiz do XML deve ser pedRegEvento")
    inf = root.find(f"{{{NFSE_NS}}}infPedReg")
    if inf is None:
        inf = root.find("infPedReg")
    if inf is None:
        raise SefinXmlDSigError("Elemento infPedReg não encontrado")
    return sign_referenced_element(
        root=root,
        target=inf,
        pfx_bytes=pfx_bytes,
        password=password,
    )


def sign_referenced_element(
    *,
    root: etree._Element,
    target: etree._Element,
    pfx_bytes: bytes,
    password: str = "",
) -> bytes:
    """Assina o elemento `target` (atributo Id) e anexa Signature como irmão."""
    ref_id = target.get("Id") or target.get("id")
    if not ref_id:
        raise SefinXmlDSigError("Elemento assinado exige atributo Id")
    if "Id" not in target.attrib and "id" in target.attrib:
        target.set("Id", ref_id)
        del target.attrib["id"]

    for old in list(root):
        if _local(old.tag) == "Signature":
            root.remove(old)

    for element in root.iter("*"):
        if element.text is not None and not element.text.strip():
            element.text = None

    key, cert = _load_key_cert(pfx_bytes, password)
    key_pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    cert_pem = cert.public_bytes(Encoding.PEM)

    signer = _XMLSignerSha1(
        method=methods.enveloped,
        signature_algorithm="rsa-sha1",
        digest_algorithm="sha1",
        c14n_algorithm=C14N_ALG,
    )
    signer.excise_empty_xmlns_declarations = True
    signer.namespaces = {None: DSIG_NS}

    try:
        signed_root = signer.sign(
            root,
            key=key_pem,
            cert=cert_pem,
            reference_uri=f"#{ref_id}",
        )
    except Exception as exc:  # noqa: BLE001
        raise SefinXmlDSigError(f"Falha XMLDSig: {exc}") from exc

    element_signed = signed_root.find(f".//*[@Id='{ref_id}']")
    signature = _find_signature(signed_root)
    if element_signed is None or signature is None:
        raise SefinXmlDSigError("Assinatura não gerou Signature/Reference esperados")
    parent = element_signed.getparent()
    if parent is None:
        raise SefinXmlDSigError("Elemento assinado sem pai")
    if signature.getparent() is not parent or list(parent)[-1] is not signature:
        parent.append(signature)

    return etree.tostring(signed_root, xml_declaration=True, encoding="UTF-8")


def verify_dps_has_signature(dps_xml: bytes | str) -> bool:
    root = safe_fromstring(dps_xml)
    return _find_signature(root) is not None


def _find_signature(root: etree._Element) -> etree._Element | None:
    for el in root.iter():
        if _local(el.tag) == "Signature" and el is not root:
            if any(_local(c.tag) == "SignatureValue" for c in el):
                return el
    return None


def _load_key_cert(pfx_bytes: bytes, password: str):
    pwd = password.encode() if password else None
    try:
        key, cert, _chain = pkcs12.load_key_and_certificates(pfx_bytes, pwd)
    except Exception as exc:  # noqa: BLE001
        raise SefinXmlDSigError("PFX inválido para assinatura") from exc
    if key is None or cert is None:
        raise SefinXmlDSigError("PFX sem chave/certificado")
    return key, cert


def _local(tag: str) -> str:
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return str(tag)
