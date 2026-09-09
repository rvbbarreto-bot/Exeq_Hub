"""Parse XML distribuição DFe."""

from __future__ import annotations

import base64
import gzip

import pytest

from integrations.sefaz_nfe.distribuicao.parse import (
    decode_doc_zip,
    detect_schema_type,
    parse_distribuicao_xml,
)
from integrations.sefaz_nfe.distribuicao.stub_xml import build_stub_res_nfe_xml


def test_detect_schema_res_nfe():
    xml = build_stub_res_nfe_xml(access_key="35260111222333000181550010000000011234567890")
    assert detect_schema_type(xml) == "resNFe"


def test_parse_res_nfe_fields():
    key = "35260111222333000181550010000000011234567890"
    xml = build_stub_res_nfe_xml(
        access_key=key,
        issuer_cnpj="11222333000181",
        issuer_name="FORNECEDOR TESTE",
        total="2500.50",
    )
    parsed = parse_distribuicao_xml(nsu="1", xml_bytes=xml)
    assert parsed.schema_type == "resNFe"
    assert parsed.access_key == key
    assert parsed.issuer_cnpj == "11222333000181"
    assert parsed.issuer_name == "FORNECEDOR TESTE"
    assert parsed.total_cents == 250050
    assert parsed.issue_date.isoformat() == "2026-01-15"
    assert len(parsed.xml_hash) == 64


def test_decode_doc_zip_roundtrip():
    xml = build_stub_res_nfe_xml(access_key="35260111222333000181550010000000011234567890")
    payload = base64.b64encode(gzip.compress(xml)).decode("ascii")
    decoded = decode_doc_zip(nsu="1", schema_hint="resNFe", payload=payload)
    assert decoded == xml
