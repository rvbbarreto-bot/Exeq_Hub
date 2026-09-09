"""Fixtures SOAP retDistDFeInt para testes HTTP."""

from __future__ import annotations

import base64
import gzip

from integrations.sefaz_nfe.distribuicao.stub_xml import build_stub_res_nfe_xml

SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
NFE_NS = "http://www.portalfiscal.inf.br/nfe"


def _doc_zip_payload(*, access_key: str) -> str:
    xml = build_stub_res_nfe_xml(access_key=access_key)
    return base64.b64encode(gzip.compress(xml)).decode("ascii")


def build_soap_ret_dist(
    *,
    c_stat: str,
    x_motivo: str,
    ult_nsu: str = "000000000000000",
    max_nsu: str = "000000000000000",
    doc_zips: list[tuple[str, str, str]] | None = None,
) -> str:
    """doc_zips: [(nsu, schema, b64gzip), ...]"""
    docs_xml = ""
    for nsu, schema, payload in doc_zips or []:
        docs_xml += f'<docZip NSU="{nsu}" schema="{schema}">{payload}</docZip>'

    lote = f"<loteDistDFeInt>{docs_xml}</loteDistDFeInt>" if docs_xml else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:soap12="{SOAP_ENV}">
  <soap12:Body>
    <nfeDistDFeInteresseResponse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDistDFeInteresseResult>
        <retDistDFeInt versao="1.01" xmlns="{NFE_NS}">
          <tpAmb>2</tpAmb>
          <cStat>{c_stat}</cStat>
          <xMotivo>{x_motivo}</xMotivo>
          <dhResp>2026-01-15T10:00:00-03:00</dhResp>
          <ultNSU>{ult_nsu}</ultNSU>
          <maxNSU>{max_nsu}</maxNSU>
          {lote}
        </retDistDFeInt>
      </nfeDistDFeInteresseResult>
    </nfeDistDFeInteresseResponse>
  </soap12:Body>
</soap12:Envelope>"""


def soap_138_one_doc(*, access_key: str, nsu: str = "000000000000001") -> str:
    payload = _doc_zip_payload(access_key=access_key)
    return build_soap_ret_dist(
        c_stat="138",
        x_motivo="Documento(s) localizado(s)",
        ult_nsu="000000000000000",
        max_nsu=nsu,
        doc_zips=[(nsu, "resNFe", payload)],
    )


def soap_137(*, ult_nsu: str = "000000000000002") -> str:
    return build_soap_ret_dist(
        c_stat="137",
        x_motivo="Nenhum documento localizado",
        ult_nsu=ult_nsu,
        max_nsu=ult_nsu,
    )


def soap_656() -> str:
    return build_soap_ret_dist(
        c_stat="656",
        x_motivo="Rejeicao: Consumo Indevido",
        ult_nsu="000000000000000",
        max_nsu="000000000000000",
    )
