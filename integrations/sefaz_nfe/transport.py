"""HTTP + mTLS SOAP NF-e (NFeAutorizacao4 / NFeRecepcaoEvento4)."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)

SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
NFE_WS_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4"
EVENTO_WS_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4"


@dataclass(frozen=True)
class SefazHttpResponse:
    http_status: int
    body: str
    c_stat: str = ""
    x_motivo: str = ""
    protocol: str = ""
    access_key: str = ""


def _pfx_to_pem_files(pfx_bytes: bytes, password: str) -> tuple[Path, Path, tempfile.TemporaryDirectory]:
    """Converte PFX em cert+key PEM temporários (requests SSL)."""
    pwd = password.encode("utf-8") if password else None
    key, cert, _chain = pkcs12.load_key_and_certificates(pfx_bytes, pwd)
    if key is None or cert is None:
        raise RuntimeError("PFX sem chave/certificado")
    tmp = tempfile.TemporaryDirectory(prefix="exeq-nfe-")
    base = Path(tmp.name)
    cert_path = base / "cert.pem"
    key_path = base / "key.pem"
    cert_path.write_bytes(cert.public_bytes(Encoding.PEM))
    key_path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    return cert_path, key_path, tmp


def _soap_envelope(*, body_xml: str, soap_action_ns: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:soap12="{SOAP_ENV}"'
        f' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        f' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
        f"<soap12:Body>"
        f'<nfeDadosMsg xmlns="{soap_action_ns}">{body_xml}</nfeDadosMsg>'
        f"</soap12:Body></soap12:Envelope>"
    )


def _first_text(xml: str, *names: str) -> str:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag in names and el.text:
            return el.text.strip()
    return ""


def post_nfe_autorizacao(
    *,
    url: str,
    envi_nfe_xml: bytes | str,
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
) -> SefazHttpResponse:
    body_inner = envi_nfe_xml.decode("utf-8") if isinstance(envi_nfe_xml, bytes) else envi_nfe_xml
    # strip declaration for embedding
    body_inner = re.sub(r"<\?xml[^?]*\?>", "", body_inner).strip()
    soap = _soap_envelope(body_xml=body_inner, soap_action_ns=NFE_WS_NS)
    cert_path, key_path, tmp = _pfx_to_pem_files(pfx_bytes, password)
    try:
        resp = requests.post(
            url,
            data=soap.encode("utf-8"),
            headers={
                "Content-Type": "application/soap+xml; charset=utf-8",
            },
            cert=(str(cert_path), str(key_path)),
            timeout=timeout,
        )
        text = resp.text or ""
        return SefazHttpResponse(
            http_status=resp.status_code,
            body=text[:20_000],
            c_stat=_first_text(text, "cStat"),
            x_motivo=_first_text(text, "xMotivo"),
            protocol=_first_text(text, "nProt"),
            access_key=_first_text(text, "chNFe"),
        )
    finally:
        tmp.cleanup()


def post_nfe_evento(
    *,
    url: str,
    evento_xml: bytes | str,
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
) -> SefazHttpResponse:
    body_inner = evento_xml.decode("utf-8") if isinstance(evento_xml, bytes) else evento_xml
    body_inner = re.sub(r"<\?xml[^?]*\?>", "", body_inner).strip()
    soap = _soap_envelope(body_xml=body_inner, soap_action_ns=EVENTO_WS_NS)
    cert_path, key_path, tmp = _pfx_to_pem_files(pfx_bytes, password)
    try:
        resp = requests.post(
            url,
            data=soap.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            cert=(str(cert_path), str(key_path)),
            timeout=timeout,
        )
        text = resp.text or ""
        return SefazHttpResponse(
            http_status=resp.status_code,
            body=text[:20_000],
            c_stat=_first_text(text, "cStat"),
            x_motivo=_first_text(text, "xMotivo"),
            protocol=_first_text(text, "nProt"),
            access_key=_first_text(text, "chNFe"),
        )
    finally:
        tmp.cleanup()
