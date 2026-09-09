"""Stub resNFe para testes de distribuição."""

from __future__ import annotations

NFE_NS = "http://www.portalfiscal.inf.br/nfe"


def build_stub_res_nfe_xml(
    *,
    access_key: str,
    issuer_cnpj: str = "11222333000181",
    issuer_name: str = "FORNECEDOR STUB LTDA",
    recipient_cnpj: str = "37229907000137",
    number: int = 1,
    series: int = 1,
    issue_date: str = "2026-01-15",
    total: str = "1000.00",
) -> bytes:
    ch = "".join(c for c in access_key if c.isdigit())[:44]
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<resNFe xmlns="{NFE_NS}" versao="1.01">
  <chNFe>{ch}</chNFe>
  <CNPJ>{issuer_cnpj}</CNPJ>
  <xNome>{issuer_name}</xNome>
  <IE>123456789012</IE>
  <dhEmi>{issue_date}T10:00:00-03:00</dhEmi>
  <tpNF>1</tpNF>
  <vNF>{total}</vNF>
  <digVal>stub</digVal>
  <dhRecb>{issue_date}T10:01:00-03:00</dhRecb>
  <nProt>135260000000000</nProt>
  <cSitNFe>1</cSitNFe>
</resNFe>""".encode("utf-8")
