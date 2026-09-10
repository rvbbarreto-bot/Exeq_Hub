"""DANFE Modelo 55 MOC v2 — testes Phase 4."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from integrations.sefaz_nfe.danfe.barcode import access_key_barcode_drawing, barcode_payload
from integrations.sefaz_nfe.danfe.checklist import evaluate_danfe_checklist
from integrations.sefaz_nfe.danfe.formatters import digits_only, format_access_key
from integrations.sefaz_nfe.danfe.layout import A4_PORTRAIT, mm_to_pt
from integrations.sefaz_nfe.danfe.pagination import plan_pages
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, render_danfe_moc_pdf
from integrations.sefaz_nfe.danfe.viewmodel import build_danfe_viewmodel
from integrations.sefaz_nfe.tests.danfe_fixtures import xml_with_items as _xml_with_items


def test_page_geometry_a4_portrait():
    xml = _xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml)
    reader = PdfReader(BytesIO(pdf))
    box = reader.pages[0].mediabox
    assert abs(float(box.width) - mm_to_pt(A4_PORTRAIT.width_mm)) < 5
    assert abs(float(box.height) - mm_to_pt(A4_PORTRAIT.height_mm)) < 5


def test_access_key_matches_xml():
    xml = _xml_with_items(1)
    vm = build_danfe_viewmodel(xml)
    pdf = render_danfe_moc_pdf(xml)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    key = digits_only(vm.access_key)
    assert len(key) == 44
    assert format_access_key(key) in text or key in text.replace(" ", "")


def test_barcode_payload_44_digits():
    xml = _xml_with_items(1)
    vm = build_danfe_viewmodel(xml)
    assert len(barcode_payload(vm.access_key)) == 44
    drawing = access_key_barcode_drawing(vm.access_key)
    assert drawing.width > 0
    assert drawing.height >= mm_to_pt(8) * 0.9


def test_checklist_passes_minimal_nfe():
    xml = _xml_with_items(1)
    result = evaluate_danfe_checklist(xml)
    assert result.passed["pdf_valido"]
    assert result.passed["titulo_danfe"]
    assert result.passed["chave_acesso_44"]
    assert result.ok


@pytest.mark.parametrize("n_items", [1, 5, 10, 20, 50, 100])
def test_pagination_page_count(n_items):
    xml = _xml_with_items(n_items)
    vm = build_danfe_viewmodel(xml)
    pages = plan_pages(vm)
    pdf = render_danfe_moc_pdf(xml)
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == len(pages)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    assert f"Folha 1/{len(pages)}" in text


def test_long_description_wraps():
    long_desc = "X" * 200
    xml = _xml_with_items(1, desc=long_desc)
    pdf = render_danfe_moc_pdf(xml)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "XXXX" in text


def test_inf_cpl_rendered():
    xml = _xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml)
    assert pdf.startswith(b"%PDF")
    from pypdf import PdfReader
    from io import BytesIO

    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "INFORMAÇÕES COMPLEMENTARES" in text.upper()


def test_layout_version_metadata():
    xml = _xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml)
    meta = PdfReader(BytesIO(pdf)).metadata
    assert LAYOUT_VERSION in str(meta.get("/Subject") or "")


def test_csosn_not_relabeled_as_cst():
    xml = _xml_with_items(1)
    vm = build_danfe_viewmodel(xml)
    assert vm.items[0].tax_classification.kind == "CSOSN"
    assert vm.items[0].tax_classification.code == "102"


def test_multipage_continuation_header_and_folha():
    xml = _xml_with_items(35)
    pdf = render_danfe_moc_pdf(xml)
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == 2
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    assert "Folha 1/2" in text
    assert "Folha 2/2" in text
    p2 = reader.pages[1].extract_text() or ""
    assert "IDENTIFICAÇÃO DO EMITENTE" in p2.upper()
    assert "DANFE" in p2


def test_issqn_block_present():
    xml = _xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "ISSQN" in text.upper()


def test_item_grid_includes_fiscal_columns():
    xml = _xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "BC ICMS" in text.upper()
    assert "ALQ ICMS" in text.upper()
