"""Calibração 2.7 — blocos dest/transporte/tax CONSTRUFORTI side-by-side."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.sefaz_nfe.danfe.calibrate import (
    CONSTRUFORTI_DEST_ROW1_RAW_MM,
    CONSTRUFORTI_PRODUCT_WIDTHS_RAW_MM,
    CONSTRUFORTI_TAX_ROW2_MEASURED_RAW_MM,
    DELIVERY_ROW2_WIDTHS_CONSTRUFORTI_MM,
    DEST_ROW1_WIDTHS_CONSTRUFORTI_MM,
    DEST_ROW2_WIDTHS_CONSTRUFORTI_MM,
    DEST_ROW3_WIDTHS_CONSTRUFORTI_MM,
    ITEM_COL_WIDTHS_CONSTRUFORTI_MM,
    TAX_ROW1_WIDTHS_CONSTRUFORTI_MM,
    TAX_ROW2_WIDTHS_CONSTRUFORTI_MM,
    TRANSPORT_ROW1_WIDTHS_CONSTRUFORTI_MM,
    measure_vertical_grid_widths_mm,
    scale_widths_to_content,
)
from integrations.sefaz_nfe.danfe.layout import (
    DELIVERY_ROW2_WIDTHS_MM,
    DEST_ROW1_WIDTHS_MM,
    DEST_ROW2_WIDTHS_MM,
    DEST_ROW3_WIDTHS_MM,
    ITEM_COL_WIDTHS_MM,
    TAX_ROW1_WIDTHS_MM,
    TAX_ROW2_WIDTHS_MM,
    TRANSPORT_ROW1_WIDTHS_MM,
    TRANSPORT_ROW2_WIDTHS_MM,
    TRANSPORT_ROW3_WIDTHS_MM,
    content_width_mm,
)
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION

REF_PNG = (
    Path(__file__).resolve().parents[3]
    / ".storage"
    / "danfe_visual_compare"
    / "CONSTRUFORTI_NF_3925"
    / "p0.reference.dpi150.png"
)

_BLOCK_WIDTHS = (
    DEST_ROW1_WIDTHS_MM,
    DEST_ROW2_WIDTHS_MM,
    DEST_ROW3_WIDTHS_MM,
    DELIVERY_ROW2_WIDTHS_MM,
    TAX_ROW1_WIDTHS_MM,
    TAX_ROW2_WIDTHS_MM,
    TRANSPORT_ROW1_WIDTHS_MM,
    TRANSPORT_ROW2_WIDTHS_MM,
    TRANSPORT_ROW3_WIDTHS_MM,
)


@pytest.mark.skipif(not REF_PNG.is_file(), reason="PNG referencia CONSTRUFORTI ausente")
def test_measure_construforti_product_grid_matches_constants():
    measured = measure_vertical_grid_widths_mm(REF_PNG, y_top_mm=178.0, y_bottom_mm=192.0)
    assert len(measured) == 13
    for got, expected in zip(measured, CONSTRUFORTI_PRODUCT_WIDTHS_RAW_MM, strict=True):
        assert abs(got - expected) <= 1.5, f"col diff {got} vs {expected}"


@pytest.mark.skipif(not REF_PNG.is_file(), reason="PNG referencia CONSTRUFORTI ausente")
def test_measure_construforti_dest_row1_matches_constants():
    measured = measure_vertical_grid_widths_mm(REF_PNG, y_top_mm=85.8, y_bottom_mm=94.3)
    assert len(measured) == 3
    for got, expected in zip(measured, CONSTRUFORTI_DEST_ROW1_RAW_MM, strict=True):
        assert abs(got - expected) <= 1.5


@pytest.mark.skipif(not REF_PNG.is_file(), reason="PNG referencia CONSTRUFORTI ausente")
def test_measure_construforti_tax_row2_matches_constants():
    measured = measure_vertical_grid_widths_mm(REF_PNG, y_top_mm=136.3, y_bottom_mm=144.8)
    assert len(measured) == 6
    for got, expected in zip(measured, CONSTRUFORTI_TAX_ROW2_MEASURED_RAW_MM, strict=True):
        assert abs(got - expected) <= 1.5


def test_layout_item_columns_synced_with_calibrate():
    assert len(ITEM_COL_WIDTHS_MM) == 13
    assert abs(sum(ITEM_COL_WIDTHS_MM) - content_width_mm()) <= 0.5
    for a, b in zip(ITEM_COL_WIDTHS_MM, ITEM_COL_WIDTHS_CONSTRUFORTI_MM, strict=True):
        assert abs(a - b) <= 0.3


@pytest.mark.parametrize(
    ("layout_widths", "calibrated"),
    [
        (DEST_ROW1_WIDTHS_MM, DEST_ROW1_WIDTHS_CONSTRUFORTI_MM),
        (DEST_ROW2_WIDTHS_MM, DEST_ROW2_WIDTHS_CONSTRUFORTI_MM),
        (DEST_ROW3_WIDTHS_MM, DEST_ROW3_WIDTHS_CONSTRUFORTI_MM),
        (DELIVERY_ROW2_WIDTHS_MM, DELIVERY_ROW2_WIDTHS_CONSTRUFORTI_MM),
        (TAX_ROW1_WIDTHS_MM, TAX_ROW1_WIDTHS_CONSTRUFORTI_MM),
        (TAX_ROW2_WIDTHS_MM, TAX_ROW2_WIDTHS_CONSTRUFORTI_MM),
        (TRANSPORT_ROW1_WIDTHS_MM, TRANSPORT_ROW1_WIDTHS_CONSTRUFORTI_MM),
    ],
)
def test_block_rows_synced_with_calibrate(layout_widths, calibrated):
    for a, b in zip(layout_widths, calibrated, strict=True):
        assert abs(a - b) <= 0.3


def test_block_row_widths_sum_to_content():
    cw = content_width_mm()
    for widths in _BLOCK_WIDTHS:
        assert abs(sum(widths) - cw) <= 0.5, f"sum={sum(widths)} widths={widths}"


def test_scale_widths_to_content():
    scaled = scale_widths_to_content((10.0, 20.0))
    assert abs(sum(scaled) - content_width_mm()) <= 0.1


def test_layout_version_27():
    assert LAYOUT_VERSION == "exeq-danfe-2.7.7-spec"
