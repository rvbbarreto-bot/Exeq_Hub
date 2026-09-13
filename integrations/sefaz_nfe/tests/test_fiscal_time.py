"""Horários fiscais — conversão local e ISO SEFAZ."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from integrations.sefaz_nfe.danfe_nfce.format import format_dh_emi
from integrations.sefaz_nfe.fiscal_time import format_fiscal_display, format_fiscal_iso, parse_fiscal_datetime
from integrations.sefaz_nfe.parse import parse_autorizacao_response
from integrations.sefaz_nfe.xml_nfce import build_nfce_xml


def test_format_fiscal_display_converts_utc_to_local():
    # 2026-09-06 02:19 UTC = 2026-09-05 23:19 BRT
    assert format_fiscal_display("2026-09-06T02:19:00+00:00") == "05/09/2026 23:19"
    assert format_dh_emi("2026-09-06T02:19:00+00:00") == "05/09/2026 23:19"


def test_format_fiscal_iso_has_colon_offset():
    dt = datetime(2026, 9, 5, 23, 19, 45, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert format_fiscal_iso(dt) == "2026-09-05T23:19:45-03:00"


def test_build_nfce_xml_uses_header_dh_emi():
    snap = {
        "emitente": {
            "cnpj": "61536366000174",
            "name": "EMIT",
            "crt": "simples_nacional",
            "address": {"uf": "SP", "codigo_ibge": "3550308"},
        },
        "header": {
            "series": 1,
            "number": 1,
            "tp_amb": "2",
            "issue_date": "2026-09-05",
            "dh_emi": "2026-09-05T23:19:45-03:00",
            "csc_id": "1",
            "csc_token": "X",
        },
        "items": [
            {
                "line": 1,
                "code": "A",
                "description": "Item",
                "ncm": "21069090",
                "cfop": "5102",
                "unit": "UN",
                "quantity": "1",
                "unit_price_cents": 100,
                "total_cents": 100,
                "origin": "0",
                "csosn": "102",
                "taxes": {},
            }
        ],
        "totals": {"products_cents": 100, "total_cents": 100},
        "payment": {"method": "17", "amount_cents": 100},
    }
    xml = build_nfce_xml(snapshot=snap).decode()
    assert "<dhEmi>2026-09-05T23:19:45-03:00</dhEmi>" in xml
    assert "T12:00:00" not in xml


def test_parse_autorizacao_extracts_dh_recbto():
    body = """
    <retEnviNFe>
      <infProt>
        <cStat>100</cStat>
        <nProt>135260000000001</nProt>
        <dhRecbto>2026-09-05T23:19:46-03:00</dhRecbto>
      </infProt>
    </retEnviNFe>
    """
    parsed = parse_autorizacao_response(body)
    assert parsed.protocol == "135260000000001"
    assert parsed.dh_recbto == "2026-09-05T23:19:46-03:00"


def test_parse_fiscal_datetime_accepts_sefaz_offset():
    dt = parse_fiscal_datetime("2026-09-05T23:19:45-03:00")
    assert dt is not None
    assert dt.hour == 23
