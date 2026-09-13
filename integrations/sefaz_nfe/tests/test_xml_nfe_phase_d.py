"""Fase D — XML NF-e com fatura e transporte."""

from __future__ import annotations

from integrations.sefaz_nfe.tests.danfe_fixtures import xml_rich_blocks_homolog
from integrations.sefaz_nfe.xml_nfe import build_nfe_xml
from integrations.sefaz_nfe.tests.test_nfe_proc import _SNAP


def test_xml_includes_billing_and_transport_blocks():
    snap = dict(_SNAP)
    snap["billing"] = {
        "nFat": "001",
        "vOrig": "50.00",
        "vLiq": "50.00",
        "duplicates": [{"nDup": "001", "dVenc": "2026-09-01", "vDup": "50.00"}],
    }
    snap["transport"] = {
        "modFrete": "0",
        "carrier": {"name": "Carrier X", "document": "12345678000199", "uf": "SP"},
        "volume": {"qVol": "1", "pesoB": "1.000"},
        "vehicle": {"placa": "XYZ9A99", "uf": "SP"},
    }
    xml = build_nfe_xml(snapshot=snap).decode("utf-8")
    assert "<nFat>001</nFat>" in xml
    assert "<nDup>001</nDup>" in xml
    assert "<transporta>" in xml
    assert "<vol>" in xml
    assert "<veicTransp>" in xml
    assert "<placa>XYZ9A99</placa>" in xml


def test_rich_fixture_xml_authorized_proc():
    xml = xml_rich_blocks_homolog()
    text = xml.decode("utf-8")
    assert "nfeProc" in text or "<NFe" in text
