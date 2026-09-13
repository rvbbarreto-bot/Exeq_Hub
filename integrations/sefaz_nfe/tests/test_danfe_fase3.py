"""Fase 3 — grid vertical MOC + layout 2.3."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader
from pypdf.generic import ArrayObject

from integrations.sefaz_nfe.danfe.layout import (
    ITEM_COL_WIDTHS_MM,
    item_column_offsets_mm,
)
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, render_danfe_moc_pdf
from integrations.sefaz_nfe.tests.danfe_fixtures import xml_with_items


@pytest.fixture(autouse=True)
def _deterministic_fonts(monkeypatch):
    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render_moc._fonts",
        lambda: {"title": "Helvetica-Bold", "body": "Helvetica", "bold": "Helvetica-Bold"},
    )


def test_item_column_offsets_has_bounds_for_spec_columns():
    bounds = item_column_offsets_mm()
    assert len(bounds) == len(ITEM_COL_WIDTHS_MM) + 1
    assert abs(bounds[-1] - sum(ITEM_COL_WIDTHS_MM)) < 0.01


def test_layout_version_fase3():
    assert LAYOUT_VERSION == "exeq-danfe-2.7.7-spec"


def _pdf_content_streams(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        contents = page.get_contents()
        if contents is None:
            continue
        streams = contents if isinstance(contents, ArrayObject) else [contents]
        for stream in streams:
            parts.append(stream.get_data().decode("latin-1", errors="ignore"))
    return "\n".join(parts)


def test_pdf_renders_with_grid_lines():
    """PDF com itens deve conter operadores de linha (grid vertical)."""
    pdf = render_danfe_moc_pdf(xml_with_items(3))
    assert pdf.startswith(b"%PDF")
    streams = _pdf_content_streams(pdf)
    assert " l" in streams
    assert streams.count(" l") >= len(item_column_offsets_mm()) - 2
    reader = PdfReader(BytesIO(pdf))
    text = reader.pages[0].extract_text() or ""
    assert "SKU1" in text
