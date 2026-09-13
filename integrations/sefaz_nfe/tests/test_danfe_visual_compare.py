"""Testes — comparacao visual DANFE vs referencia."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.sefaz_nfe.danfe.render_moc import render_danfe_moc_pdf
from integrations.sefaz_nfe.danfe.visual_compare import (
    analyze_pdf_markers,
    build_exeq_candidate_pdfs,
    compare_reference_to_exeq,
    pick_exeq_fixture,
)
from integrations.sefaz_nfe.tests.danfe_fixtures import xml_with_items


@pytest.fixture(autouse=True)
def _fonts(monkeypatch):
    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render_moc._fonts",
        lambda: {"title": "Helvetica-Bold", "body": "Helvetica", "bold": "Helvetica-Bold"},
    )


def test_pick_exeq_fixture_by_pages():
    assert pick_exeq_fixture(1) == "rich_blocks_homolog"
    assert pick_exeq_fixture(2) == "multi_2page_homolog"


def test_build_exeq_candidates_are_pdfs():
    pdfs = build_exeq_candidate_pdfs()
    assert set(pdfs) >= {"rich_blocks_homolog", "multi_2page_homolog"}
    for data in pdfs.values():
        assert data.startswith(b"%PDF")


def test_compare_reference_to_exeq_creates_side_by_side(tmp_path):
    ref_pdf = render_danfe_moc_pdf(xml_with_items(1))
    exeq_pdf = render_danfe_moc_pdf(xml_with_items(3))
    report = compare_reference_to_exeq(
        ref_pdf,
        exeq_pdf,
        reference_name="ref_test",
        exeq_fixture="minimal_1item_homolog",
        output_dir=tmp_path,
        dpi=72,
    )
    assert report.page_pairs
    assert report.page_pairs[0].side_by_side_path.is_file()
    assert analyze_pdf_markers(ref_pdf).page_count == 1


def test_run_reference_batch_skips_missing_dir(tmp_path):
    from integrations.sefaz_nfe.danfe.visual_compare import run_reference_batch

    with pytest.raises(FileNotFoundError):
        run_reference_batch(reference_dir=tmp_path / "missing", output_dir=tmp_path / "out")
