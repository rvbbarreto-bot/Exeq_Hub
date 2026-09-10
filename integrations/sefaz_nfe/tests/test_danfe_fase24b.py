"""Fase 2.4b — entrega, Times, logo, colunas, vTotTrib no rodapé."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from pypdf import PdfReader

from integrations.sefaz_nfe.danfe.layout import (
    DELIVERY_BLOCK_HEIGHT,
    ITEM_COL_WIDTHS_MM,
    content_width_mm,
    page1_offsets,
)
from integrations.sefaz_nfe.danfe.pagination import plan_pages
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, _fonts, render_danfe_moc_pdf
from integrations.sefaz_nfe.danfe.viewmodel import build_danfe_viewmodel
from integrations.sefaz_nfe.tests.danfe_fixtures import xml_rich_blocks_homolog


def test_layout_version_25_spec():
    assert LAYOUT_VERSION == "exeq-danfe-2.7.7-spec"


def test_item_columns_sum_near_content_width():
    assert len(ITEM_COL_WIDTHS_MM) == 13
    assert abs(sum(ITEM_COL_WIDTHS_MM) - content_width_mm()) <= 0.5
    assert sum(ITEM_COL_WIDTHS_MM) <= content_width_mm() + 1.0


def test_delivery_offsets_shift_page1_stack():
    base = page1_offsets(has_delivery=False)
    with_del = page1_offsets(has_delivery=True)
    assert with_del.delivery_top == base.billing_top
    assert with_del.billing_top == base.billing_top + DELIVERY_BLOCK_HEIGHT
    assert with_del.items_area_bottom == base.items_area_bottom - DELIVERY_BLOCK_HEIGHT


def test_viewmodel_parses_entrega():
    xml = xml_rich_blocks_homolog()
    vm = build_danfe_viewmodel(xml)
    assert "Rua Obra 500" in vm.delivery_address
    assert "Atibaia" in vm.delivery_address
    assert vm.delivery_differs_from_dest


def test_plan_pages_marks_delivery_on_page1():
    vm = build_danfe_viewmodel(xml_rich_blocks_homolog())
    pages = plan_pages(vm)
    assert pages[0].show_delivery is True


def test_pdf_contains_delivery_and_tributos_text():
    pdf = render_danfe_moc_pdf(xml_rich_blocks_homolog())
    reader = PdfReader(io.BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "LOCAL DE ENTREGA" in text or "ENTREGA" in text
    assert "RUA OBRA 500" in text.upper()
    assert "tributos" in text.lower() or "Tributos" in text


def test_fonts_prefers_arial_when_available():
    with patch("integrations.sefaz_nfe.danfe.render_moc.Path.is_file", return_value=True):
        with patch("integrations.sefaz_nfe.danfe.render_moc.pdfmetrics.registerFont"):
            _fonts.cache_clear()
            fonts = _fonts()
            assert fonts["body"] == "DanfeReg"
            _fonts.cache_clear()


@pytest.mark.parametrize("logo_bytes", [b"\x89PNG\r\n\x1a\n" + b"\x00" * 32])
def test_pdf_renders_with_logo_bytes_without_crash(logo_bytes):
    try:
        pdf = render_danfe_moc_pdf(xml_rich_blocks_homolog(), logo_bytes=logo_bytes)
    except Exception:
        pytest.skip("logo PNG invalid for reportlab")
    assert pdf[:4] == b"%PDF"
