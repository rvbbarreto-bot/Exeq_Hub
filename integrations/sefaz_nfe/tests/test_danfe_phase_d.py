"""Fase D — cabeçalho p2, blocos estruturados, view model rico."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from integrations.sefaz_nfe.danfe.pagination import plan_pages
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, render_danfe_moc_pdf
from integrations.sefaz_nfe.danfe.viewmodel import build_danfe_viewmodel
from integrations.sefaz_nfe.tests.danfe_fixtures import (
    xml_multipage_homolog,
    xml_rich_blocks_homolog,
    xml_with_items,
)


@pytest.fixture(autouse=True)
def _deterministic_fonts(monkeypatch):
    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render_moc._fonts",
        lambda: {"title": "Helvetica-Bold", "body": "Helvetica", "bold": "Helvetica-Bold"},
    )


def test_layout_version_phase_d():
    xml = xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml)
    meta = PdfReader(BytesIO(pdf)).metadata
    assert LAYOUT_VERSION in str(meta.get("/Subject") or "")
    assert LAYOUT_VERSION.startswith("exeq-danfe-2.")


def test_rich_viewmodel_parses_billing_transport():
    vm = build_danfe_viewmodel(xml_rich_blocks_homolog())
    assert vm.invoice_number_fat == "001"
    assert len(vm.duplicates) == 2
    assert vm.duplicates[0].number == "001"
    assert vm.duplicates[1].number == "002"
    assert vm.transport.carrier_name == "TRANSPORTADORA EXEMPLO LTDA"
    assert vm.transport.vehicle_plate == "ABC1D23"
    assert vm.transport.gross_weight == "10.500"
    assert vm.nature == "VENDA DE MERCADORIA"
    assert vm.emit_phone == "1144445555"
    assert vm.totals.approx_taxes == "1.50"


def test_rich_blocks_rendered_on_pdf():
    xml = xml_rich_blocks_homolog()
    pdf = render_danfe_moc_pdf(xml)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "FATURA / DUPLICATAS" in text.upper()
    assert "FATURA" in text.upper()
    assert "TRANSPORTADOR" in text.upper()
    assert "TRANSPORTADORA EXEMPLO" in text.upper()
    assert "ABC1D23" in text
    assert "NATUREZA DA OPERACAO" in text.upper() or "NATUREZA" in text.upper()
    assert "IDENTIFICAÇÃO DO EMITENTE" in text.upper()
    assert "VALOR TOTAL DA NOTA" in text.upper() or "V. NF" in text.upper()


def test_page2_full_header_without_canhoto():
    xml = xml_multipage_homolog(35)
    pdf = render_danfe_moc_pdf(xml)
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == 2
    p1 = reader.pages[0].extract_text() or ""
    p2 = reader.pages[1].extract_text() or ""
    assert "RECEBEMOS DE" in p1
    assert "PROTOCOLO DE AUTORIZACAO" in p1.upper()
    assert "RECEBEMOS DE" not in p2
    assert "IDENTIFICAÇÃO DO EMITENTE" in p2.upper()
    assert "EXEQ LAB" in p2
    assert "DANFE" in p2
    assert "FOLHA 2/2" in p2.upper()
    assert "DESTINATÁRIO" not in p2.upper()


def test_page2_uses_continuation_items_top():
    vm = build_danfe_viewmodel(xml_multipage_homolog(35))
    pages = plan_pages(vm)
    assert len(pages) == 2
    assert pages[0].show_continuation_header is False
    assert pages[1].show_continuation_header is True
    assert pages[1].items_header_top_mm < 80
    assert pages[0].items_header_top_mm > 170


def test_page2_starts_items_higher_than_page1():
    xml = xml_multipage_homolog(35)
    pdf = render_danfe_moc_pdf(xml)
    reader = PdfReader(BytesIO(pdf))
    p2 = reader.pages[1].extract_text() or ""
    assert "SKU" in p2
