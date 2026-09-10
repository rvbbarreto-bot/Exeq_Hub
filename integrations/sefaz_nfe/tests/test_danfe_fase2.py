"""Fase 2 — infCpl overflow, logo, compare estrutural, blocos ricos."""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from pypdf import PdfReader

from integrations.sefaz_nfe.danfe.compare import MOC_STRUCTURAL_MARKERS, compare_structural
from integrations.sefaz_nfe.danfe.pagination import plan_pages
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, render_danfe_moc_pdf
from integrations.sefaz_nfe.danfe.viewmodel import build_danfe_viewmodel
from integrations.sefaz_nfe.tests.danfe_fixtures import (
    xml_long_infcpl_homolog,
    xml_rich_blocks_homolog,
    xml_with_items,
)

# PNG 1×1 válido (logo mínimo para teste)
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def _deterministic_fonts(monkeypatch):
    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render_moc._fonts",
        lambda: {"title": "Helvetica-Bold", "body": "Helvetica", "bold": "Helvetica-Bold"},
    )


def test_layout_version_fase2():
    assert LAYOUT_VERSION.startswith("exeq-danfe-2.")


def test_long_infcpl_adds_continuation_page():
    xml = xml_long_infcpl_homolog(n_cpl_lines=12)
    vm = build_danfe_viewmodel(xml)
    pages = plan_pages(vm)
    assert len(pages) >= 2
    assert any(p.inf_cpl_continuation for p in pages)
    assert any(p.show_footer_info and not p.item_rows for p in pages)


def test_long_infcpl_renders_continuation_title():
    xml = xml_long_infcpl_homolog(n_cpl_lines=12)
    pdf = render_danfe_moc_pdf(xml)
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 2
    combined = "\n".join((p.extract_text() or "") for p in reader.pages)
    assert "COMPLEMENTARES" in combined.upper()
    assert "CONT" in combined.upper()


def test_logo_bytes_renders_valid_pdf():
    xml = xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml, logo_bytes=_TINY_PNG)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_rich_blocks_multiple_duplicatas():
    xml = xml_rich_blocks_homolog()
    vm = build_danfe_viewmodel(xml)
    assert len(vm.duplicates) == 2
    pdf = render_danfe_moc_pdf(xml)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "001" in text
    assert "002" in text


def test_structural_compare_passes_rich_danfe():
    xml = xml_rich_blocks_homolog()
    pdf = render_danfe_moc_pdf(xml)
    result = compare_structural(pdf, extra_markers=("FATURA / DUPLICATAS", "TRANSPORTADORA EXEMPLO"))
    assert result.ok, f"missing: {result.missing}"
    assert result.page_count == 1


def test_structural_compare_detects_missing_marker():
    xml = xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml)
    result = compare_structural(pdf, extra_markers=("TEXTO_INEXISTENTE_XYZ",))
    assert not result.ok
    assert "TEXTO_INEXISTENTE_XYZ" in result.missing


@pytest.mark.parametrize("marker", MOC_STRUCTURAL_MARKERS[:5])
def test_structural_markers_on_minimal_danfe(marker):
    pdf = render_danfe_moc_pdf(xml_with_items(1))
    result = compare_structural(pdf)
    assert result.passed.get(marker), f"missing {marker}"
