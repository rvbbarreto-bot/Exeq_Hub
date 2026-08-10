"""HTTP + mTLS SOAP NF-e (autorizacao / ret / consulta) — I4 + I5."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)

from integrations.sefaz_nfe.parse import parse_autorizacao_response, parse_evento_response

SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
NFE_WS_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4"
RET_AUTORIZACAO_WS_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRetAutorizacao4"
CONSULTA_PROTOCOLO_WS_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4"
EVENTO_WS_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4"
NFE_NS = "http://www.portalfiscal.inf.br/nfe"


@dataclass(frozen=True)
class SefazHttpResponse:
    http_status: int
    body: str
    c_stat: str = ""
    x_motivo: str = ""
    protocol: str = ""
    access_key: str = ""
    lote_c_stat: str = ""
    n_rec: str = ""


def _pfx_to_pem_files(pfx_bytes: bytes, password: str) -> tuple[Path, Path, tempfile.TemporaryDirectory]:
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


def _post_soap(
    *,
    url: str,
    body_xml: str,
    soap_action_ns: str,
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> SefazHttpResponse:
    soap = _soap_envelope(body_xml=body_xml, soap_action_ns=soap_action_ns)
    cert_path, key_path, tmp = _pfx_to_pem_files(pfx_bytes, password)
    try:
        post = session.post if session is not None else requests.post
        resp = post(
            url,
            data=soap.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            cert=(str(cert_path), str(key_path)),
            timeout=timeout,
        )
        text = resp.text or ""
        parsed = parse_autorizacao_response(text)
        return SefazHttpResponse(
            http_status=resp.status_code,
            body=text[:20_000],
            c_stat=parsed.c_stat,
            x_motivo=parsed.x_motivo,
            protocol=parsed.protocol,
            access_key=parsed.access_key,
            lote_c_stat=parsed.lote_c_stat,
            n_rec=parsed.n_rec,
        )
    finally:
        tmp.cleanup()


def post_nfe_autorizacao(
    *,
    url: str,
    envi_nfe_xml: bytes | str,
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> SefazHttpResponse:
    """POST SOAP NFeAutorizacao4 com mTLS. `session` injetável para testes."""
    body_inner = envi_nfe_xml.decode("utf-8") if isinstance(envi_nfe_xml, bytes) else envi_nfe_xml
    body_inner = re.sub(r"<\?xml[^?]*\?>", "", body_inner).strip()
    return _post_soap(
        url=url,
        body_xml=body_inner,
        soap_action_ns=NFE_WS_NS,
        pfx_bytes=pfx_bytes,
        password=password,
        timeout=timeout,
        session=session,
    )


def build_cons_reci_nfe(*, tp_amb: str, n_rec: str) -> str:
    rec = "".join(ch for ch in str(n_rec or "") if ch.isdigit())
    amb = str(tp_amb or "2").strip()[:1] or "2"
    return (
        f'<consReciNFe versao="4.00" xmlns="{NFE_NS}">'
        f"<tpAmb>{amb}</tpAmb>"
        f"<nRec>{rec}</nRec>"
        f"</consReciNFe>"
    )


def build_cons_sit_nfe(*, tp_amb: str, access_key: str) -> str:
    ch = "".join(ch for ch in str(access_key or "") if ch.isdigit())[:44]
    amb = str(tp_amb or "2").strip()[:1] or "2"
    return (
        f'<consSitNFe versao="4.00" xmlns="{NFE_NS}">'
        f"<tpAmb>{amb}</tpAmb>"
        f"<xServ>CONSULTAR</xServ>"
        f"<chNFe>{ch}</chNFe>"
        f"</consSitNFe>"
    )


def post_nfe_ret_autorizacao(
    *,
    url: str,
    n_rec: str,
    tp_amb: str = "2",
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> SefazHttpResponse:
    """POST SOAP NFeRetAutorizacao4 (consulta recibo nRec) — I5."""
    return _post_soap(
        url=url,
        body_xml=build_cons_reci_nfe(tp_amb=tp_amb, n_rec=n_rec),
        soap_action_ns=RET_AUTORIZACAO_WS_NS,
        pfx_bytes=pfx_bytes,
        password=password,
        timeout=timeout,
        session=session,
    )


def post_nfe_consulta_protocolo(
    *,
    url: str,
    access_key: str,
    tp_amb: str = "2",
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> SefazHttpResponse:
    """POST SOAP NFeConsultaProtocolo4 (consulta por chave) — I5."""
    return _post_soap(
        url=url,
        body_xml=build_cons_sit_nfe(tp_amb=tp_amb, access_key=access_key),
        soap_action_ns=CONSULTA_PROTOCOLO_WS_NS,
        pfx_bytes=pfx_bytes,
        password=password,
        timeout=timeout,
        session=session,
    )


def post_nfe_evento(
    *,
    url: str,
    evento_xml: bytes | str,
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> SefazHttpResponse:
    """POST SOAP NFeRecepcaoEvento4 (cancel 110111 / demais eventos) — I6."""
    body_inner = evento_xml.decode("utf-8") if isinstance(evento_xml, bytes) else evento_xml
    body_inner = re.sub(r"<\?xml[^?]*\?>", "", body_inner).strip()
    soap = _soap_envelope(body_xml=body_inner, soap_action_ns=EVENTO_WS_NS)
    cert_path, key_path, tmp = _pfx_to_pem_files(pfx_bytes, password)
    try:
        post = session.post if session is not None else requests.post
        resp = post(
            url,
            data=soap.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            cert=(str(cert_path), str(key_path)),
            timeout=timeout,
        )
        text = resp.text or ""
        parsed = parse_evento_response(text)
        return SefazHttpResponse(
            http_status=resp.status_code,
            body=text[:20_000],
            c_stat=parsed.c_stat,
            x_motivo=parsed.x_motivo,
            protocol=parsed.protocol,
            access_key=parsed.access_key,
            lote_c_stat=parsed.lote_c_stat,
            n_rec=parsed.n_rec,
        )
    finally:
        tmp.cleanup()


INUTILIZACAO_WS_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeInutilizacao4"


def post_nfe_inutilizacao(
    *,
    url: str,
    inut_xml: bytes | str,
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> SefazHttpResponse:
    """POST SOAP NFeInutilizacao4 — U15."""
    body_inner = inut_xml.decode("utf-8") if isinstance(inut_xml, bytes) else inut_xml
    body_inner = re.sub(r"<\?xml[^?]*\?>", "", body_inner).strip()
    soap = _soap_envelope(body_xml=body_inner, soap_action_ns=INUTILIZACAO_WS_NS)
    cert_path, key_path, tmp = _pfx_to_pem_files(pfx_bytes, password)
    try:
        post = session.post if session is not None else requests.post
        resp = post(
            url,
            data=soap.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"},
            cert=(str(cert_path), str(key_path)),
            timeout=timeout,
        )
        text = resp.text or ""
        parsed = parse_autorizacao_response(text)
        return SefazHttpResponse(
            http_status=resp.status_code,
            body=text[:20_000],
            c_stat=parsed.c_stat,
            x_motivo=parsed.x_motivo,
            protocol=parsed.protocol,
            access_key=parsed.access_key,
            lote_c_stat=parsed.lote_c_stat,
            n_rec=parsed.n_rec,
        )
    finally:
        tmp.cleanup()
