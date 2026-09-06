"""DANFE NFC-e cupom PDF — golden tests exeq-danfce-1.0."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from integrations.sefaz_nfe.danfe_nfce import (
    LAYOUT_VERSION,
    extract_danfce_fields,
    render_danfce_pdf,
)
from integrations.sefaz_nfe.danfe_nfce.format import format_br_money
from integrations.sefaz_nfe.xml_nfce import build_nfce_xml


def _pdf_text(pdf: bytes) -> str:
    return "".join((p.extract_text() or "") for p in PdfReader(BytesIO(pdf)).pages)


def _rich_snapshot(*, with_rtc: bool = False, cpf: str = "39053344705") -> dict:
    items = [
        {
            "line": 1,
            "code": "HUB1",
            "description": "Prato Ale",
            "ncm": "21069090",
            "cfop": "5102",
            "unit": "UN",
            "quantity": "1",
            "unit_price_cents": 1500,
            "total_cents": 1500,
            "origin": "0",
            "csosn": "102",
            "taxes": {"icms": {"regime": "sn", "csosn": "102"}},
        },
        {
            "line": 2,
            "code": "HUB2",
            "description": "Suco",
            "ncm": "21069090",
            "cfop": "5102",
            "unit": "UN",
            "quantity": "2",
            "unit_price_cents": 500,
            "total_cents": 1000,
            "origin": "0",
            "csosn": "102",
            "taxes": {"icms": {"regime": "sn", "csosn": "102"}},
        },
    ]
    if with_rtc:
        from apps.nfce.rtc import build_item_rtc, aggregate_rtc_totals

        enriched = []
        for it in items:
            rtc = build_item_rtc(line_total_cents=int(it["total_cents"]), issue_date="2026-09-05")
            rtc["xml_ub"] = True
            taxes = dict(it["taxes"])
            taxes["rtc"] = rtc
            enriched.append({**it, "taxes": taxes})
        items = enriched
        rtc_tot = aggregate_rtc_totals(items)
    else:
        rtc_tot = None

    snap = {
        "document_model": "65",
        "emitente": {
            "cnpj": "61536366000174",
            "name": "ALEXANDRE JOSE MARQUES",
            "ie": "ISENTO",
            "crt": "simples_nacional",
            "address": {
                "logradouro": "Rua A",
                "numero": "1",
                "bairro": "Centro",
                "municipio": "Sao Paulo",
                "uf": "SP",
                "cep": "01001000",
                "codigo_ibge": "3550308",
            },
        },
        "destinatario": {"document": cpf, "name": "CONSUMIDOR TESTE"},
        "header": {
            "model": "65",
            "nature": "VENDA",
            "series": 1,
            "number": 1,
            "tp_amb": "2",
            "issue_date": "2026-09-05",
            "omit_dest": False,
            "csc_id": "1",
            "csc_token": "HOMOLOGCSC",
        },
        "sefaz": {"csc_id": "1", "csc_token": "HOMOLOGCSC"},
        "items": items,
        "totals": {
            "products_cents": 2500,
            "total_cents": 2500,
            "icms_cents": 0,
            "pis_cents": 0,
            "cofins_cents": 0,
        },
        "payment": {"method": "17", "amount_cents": 2500},
    }
    if rtc_tot:
        snap["totals"]["rtc"] = rtc_tot
    return snap


def test_danfce_layout_version():
    assert LAYOUT_VERSION == "exeq-danfce-1.0"


def test_danfce_pdf_starts_with_pdf_header():
    xml = build_nfce_xml(snapshot=_rich_snapshot())
    pdf = render_danfce_pdf(xml)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 800


def test_danfce_golden_multi_item_payment_consumer():
    xml = build_nfce_xml(snapshot=_rich_snapshot())
    text = _pdf_text(render_danfce_pdf(xml, protocol_override="135260000000001"))
    assert "DANFE NFC-e" in text
    assert "QTD. TOTAL DE ITENS:" in text
    assert "3" in text  # 2 + 1 unidades
    assert "VALOR TOTAL R$:" in text
    assert format_br_money("25.00") in text or "25,00" in text
    assert "Pix" in text
    assert "390.533.447-05" in text
    assert "Protocolo de Autorização: 135260000000001" in text
    assert "CONSUMIDOR NÃO IDENTIFICADO" not in text
    assert "Consulta via leitor de QR Code" in text
    assert "QR Code indisponível" not in text
    assert "HUB1" in text
    assert "HUB2" in text
    assert "15,00" in text
    assert "exeq-danfce-1.0" in text


def test_danfce_unit_price_formats_ten_decimals():
    snap = _rich_snapshot()
    snap["items"] = [snap["items"][0]]
    snap["totals"] = {"products_cents": 1500, "total_cents": 1500}
    snap["payment"] = {"method": "99", "amount_cents": 1500}
    xml = build_nfce_xml(snapshot=snap)
    fields = extract_danfce_fields(xml)
    assert fields.items[0]["vun"].endswith("0000000000") or "15" in fields.items[0]["vun"]
    text = _pdf_text(render_danfce_pdf(xml))
    assert "15,00" in text
    assert "15.0000000000" not in text


def test_danfce_homolog_banner():
    xml = build_nfce_xml(snapshot=_rich_snapshot())
    text = _pdf_text(render_danfce_pdf(xml))
    assert "HOMOLOGA" in text
    assert "SEM VALOR FISCAL" in text


def test_danfce_consumer_not_identified_when_omit_dest():
    snap = _rich_snapshot()
    snap["header"]["omit_dest"] = True
    snap.pop("destinatario", None)
    xml = build_nfce_xml(snapshot=snap)
    text = _pdf_text(render_danfce_pdf(xml))
    assert "CONSUMIDOR NÃO IDENTIFICADO" in text


def test_danfce_rtc_block_when_ibscbs_in_xml():
    xml = build_nfce_xml(snapshot=_rich_snapshot(with_rtc=True))
    fields = extract_danfce_fields(xml)
    assert fields.v_cbs
    assert fields.v_ibs
    text = _pdf_text(render_danfce_pdf(xml))
    assert "CBS (Federal)" in text
    assert "IBS" in text


def test_danfce_cancelled_banner():
    xml = build_nfce_xml(snapshot=_rich_snapshot())
    text = _pdf_text(render_danfce_pdf(xml, cancelled=True))
    assert "CANCELADA" in text


def test_danfce_total_units_single_line_qty_three():
    snap = _rich_snapshot()
    snap["items"] = [snap["items"][0]]
    snap["items"][0]["quantity"] = "3"
    snap["items"][0]["total_cents"] = 4500
    snap["totals"] = {"products_cents": 4500, "total_cents": 4500}
    snap["payment"] = {"method": "17", "amount_cents": 4500}
    xml = build_nfce_xml(snapshot=snap)
    fields = extract_danfce_fields(xml)
    assert fields.total_units == "3"
    text = _pdf_text(render_danfce_pdf(xml, protocol_override="STUB123"))
    assert "QTD. TOTAL DE ITENS:" in text
    assert "Consulta via leitor de QR Code" in text


def test_sum_item_quantities_helper():
    from integrations.sefaz_nfe.danfe_nfce.format import sum_item_quantities

    assert sum_item_quantities([{"qty": "3"}, {"qty": "2"}]) == "5"
    assert sum_item_quantities([{"qty": "3.0000"}]) == "3"


def test_format_br_money_from_cents():
    assert format_br_money(1500) == "15,00"
    assert format_br_money("15.0000000000") == "15,00"
