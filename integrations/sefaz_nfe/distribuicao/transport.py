"""HTTP + mTLS SOAP NFeDistribuicaoDFe — Ambiente Nacional (NT 2014.002)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from integrations.sefaz_nfe.transport import SOAP_ENV, _pfx_to_pem_files

DIST_WS_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"
NFE_NS = "http://www.portalfiscal.inf.br/nfe"


@dataclass(frozen=True)
class DistribuicaoHttpResponse:
    http_status: int
    body: str


def build_dist_dfe_interesse(
    *,
    tp_amb: str,
    cnpj: str,
    ult_nsu: str,
    cuf_autor: str = "35",
) -> str:
    """Monta distDFeInt/distNSU (sem SOAP)."""
    amb = str(tp_amb or "2").strip()[:1] or "2"
    cnpj_d = "".join(c for c in str(cnpj or "") if c.isdigit())[:14]
    if len(cnpj_d) != 14:
        raise ValueError("CNPJ destinatário inválido")
    nsu = "".join(c for c in str(ult_nsu or "0") if c.isdigit()).zfill(15)[-15:]
    cuf = "".join(c for c in str(cuf_autor or "35") if c.isdigit())[:2] or "35"
    return (
        f'<distDFeInt versao="1.01" xmlns="{NFE_NS}">'
        f"<tpAmb>{amb}</tpAmb>"
        f"<cUFAutor>{cuf}</cUFAutor>"
        f"<CNPJ>{cnpj_d}</CNPJ>"
        f"<distNSU><ultNSU>{nsu}</ultNSU></distNSU>"
        f"</distDFeInt>"
    )


def _soap_envelope_dist(*, body_xml: str) -> str:
    inner = re.sub(r"<\?xml[^?]*\?>", "", body_xml).strip()
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap12:Envelope xmlns:soap12="{SOAP_ENV}"'
        f' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        f' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
        f"<soap12:Body>"
        f'<nfeDistDFeInteresse xmlns="{DIST_WS_NS}">'
        f"<nfeDadosMsg>{inner}</nfeDadosMsg>"
        f"</nfeDistDFeInteresse>"
        f"</soap12:Body></soap12:Envelope>"
    )


def post_nfe_distribuicao(
    *,
    url: str,
    tp_amb: str,
    cnpj: str,
    ult_nsu: str,
    cuf_autor: str,
    pfx_bytes: bytes,
    password: str = "",
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> DistribuicaoHttpResponse:
    """POST SOAP NFeDistribuicaoDFe/nfeDistDFeInteresse com mTLS."""
    body = build_dist_dfe_interesse(
        tp_amb=tp_amb,
        cnpj=cnpj,
        ult_nsu=ult_nsu,
        cuf_autor=cuf_autor,
    )
    soap = _soap_envelope_dist(body_xml=body)
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
        return DistribuicaoHttpResponse(
            http_status=resp.status_code,
            body=(resp.text or "")[:500_000],
        )
    finally:
        tmp.cleanup()
