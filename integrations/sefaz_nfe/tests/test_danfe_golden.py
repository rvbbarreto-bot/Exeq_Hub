"""Golden PDF + decode barcode — Phase 4 §3 / §31."""

from __future__ import annotations

import os

import pytest

from integrations.sefaz_nfe.danfe.barcode_decode import (
    decode_access_key_from_barcode_drawing,
    decode_access_key_from_pdf,
)
from integrations.sefaz_nfe.danfe.formatters import digits_only
from integrations.sefaz_nfe.danfe.golden import compare_pdf_to_golden, rasterize_pdf_page
from integrations.sefaz_nfe.danfe.render_moc import render_danfe_moc_pdf
from integrations.sefaz_nfe.danfe.viewmodel import build_danfe_viewmodel
from integrations.sefaz_nfe.tests.danfe_fixtures import _GOLDEN_KEY, xml_rich_blocks_homolog, xml_with_items

UPDATE_GOLDEN = os.environ.get("DANFE_UPDATE_GOLDEN", "").lower() in ("1", "true", "yes")


@pytest.fixture(autouse=True)
def _deterministic_fonts(monkeypatch):
    """Golden estável: Helvetica (evita dif Arial vs DejaVu entre ambientes)."""

    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render_moc._fonts",
        lambda: {"title": "Helvetica-Bold", "body": "Helvetica", "bold": "Helvetica-Bold"},
    )


@pytest.mark.parametrize(
    "fixture_name,n_items,tp_amb,cancelled",
    [
        ("minimal_1item_homolog", 1, "2", False),
        ("multi_5items_homolog", 5, "2", False),
        ("minimal_1item_producao", 1, "1", False),
        ("multi_2page_homolog", 35, "2", False),
        ("rich_blocks_homolog", 1, "2", False),
    ],
)
def test_golden_pdf_visual_regression(fixture_name, n_items, tp_amb, cancelled):
    if fixture_name == "rich_blocks_homolog":
        xml = xml_rich_blocks_homolog(n_items=n_items)
    else:
        xml = xml_with_items(n_items, tp_amb=tp_amb)
    pdf = render_danfe_moc_pdf(xml, cancelled=cancelled)
    assert pdf.startswith(b"%PDF")

    results = compare_pdf_to_golden(
        pdf,
        fixture_name,
        dpi=150,
        tolerance=0.04,
        update=UPDATE_GOLDEN,
    )
    assert results, "PDF sem páginas para golden"
    if fixture_name == "multi_2page_homolog":
        assert len(results) == 2, f"esperado 2 páginas, obteve {len(results)}"
    for res in results:
        assert res.passed, (
            f"golden {fixture_name} page {res.page_index}: "
            f"diff={res.diff_ratio:.4f} ref={res.reference_path}"
        )


def test_barcode_decode_from_full_pdf():
    xml = xml_with_items(1)
    vm = build_danfe_viewmodel(xml)
    pdf = render_danfe_moc_pdf(xml)
    decoded = decode_access_key_from_pdf(pdf)
    assert decoded == digits_only(vm.access_key)


def test_barcode_decode_from_isolated_drawing():
    decoded = decode_access_key_from_barcode_drawing(_GOLDEN_KEY)
    assert decoded == _GOLDEN_KEY


@pytest.mark.parametrize("dpi", [150, 300])
def test_rasterize_multi_dpi(dpi):
    xml = xml_with_items(1)
    pdf = render_danfe_moc_pdf(xml)
    img = rasterize_pdf_page(pdf, dpi=dpi, page_index=0)
    assert img.size[0] > 0 and img.size[1] > 0


def test_pdf_page_count_stable_for_fixture():
    """Regressão estrutural — mesma entrada → mesma paginação."""
    import pymupdf

    xml = xml_with_items(5)
    n1 = len(pymupdf.open(stream=render_danfe_moc_pdf(xml), filetype="pdf"))
    n2 = len(pymupdf.open(stream=render_danfe_moc_pdf(xml), filetype="pdf"))
    assert n1 == n2 == 1
