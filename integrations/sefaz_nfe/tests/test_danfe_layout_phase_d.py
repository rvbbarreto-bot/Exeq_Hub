"""Fase D — calibração layout MOC e encadeamento de blocos."""

from __future__ import annotations

from integrations.sefaz_nfe.danfe.layout import (
    A4_PORTRAIT,
    BILLING_TOP,
    CANHOTO_BOTTOM_TOP,
    CANHOTO_CUT_LINE_GAP_MM,
    CANHOTO_HEIGHT,
    PAGE_BOTTOM_MARGIN_MM,
    DEST_TOP,
    FOOTER_INFO_HEIGHT,
    FOOTER_INFO_TOP,
    ISSQN_TOP,
    HEADER_TOP,
    PAGE_TOP_MM,
    ITEM_COL_WIDTHS_MM,
    item_column_offsets_mm,
    PAGE1_BLOCKS,
    PAGE1_ITEMS_HEADER_TOP,
    TAX_TOP,
    TRANSPORT_TOP,
    block_bottom_mm,
    content_width_mm,
    items_area_bottom_mm,
    items_area_top_mm,
    verify_page1_layout_stack,
)


def test_page1_layout_stack_has_no_overlaps():
    errors = verify_page1_layout_stack()
    assert errors == [], errors


def test_page1_blocks_follow_moc_vertical_order():
    names = [b.name for b in PAGE1_BLOCKS if b.name not in {"rodape", "canhoto"}]
    assert names.index("header") < names.index("nfe_strip")
    assert names.index("nfe_strip") < names.index("destinatario")
    assert names.index("destinatario") < names.index("fatura")
    assert names.index("fatura") < names.index("imposto")
    assert names.index("imposto") < names.index("transporte")
    assert names.index("transporte") < names.index("produtos")
    assert names.index("produtos") < names.index("issqn")


def test_billing_starts_after_destinatario():
    dest = next(b for b in PAGE1_BLOCKS if b.name == "destinatario")
    billing = next(b for b in PAGE1_BLOCKS if b.name == "fatura")
    assert billing.top_mm >= block_bottom_mm(dest)


def test_items_area_fits_inside_a4():
    top = items_area_top_mm(continuation=False)
    bottom = items_area_bottom_mm()
    assert top < bottom
    assert bottom <= A4_PORTRAIT.height_mm


def test_continuation_items_start_after_header():
    cont_top = items_area_top_mm(continuation=True)
    assert cont_top > HEADER_TOP + 30


def test_item_grid_columns_match_spec_13():
    assert len(ITEM_COL_WIDTHS_MM) == 13
    assert len(item_column_offsets_mm()) == 14


def test_content_width_accommodates_item_columns():
    total_cols = sum(ITEM_COL_WIDTHS_MM)
    assert total_cols <= content_width_mm() + 20  # tolerância fonte compacta


def test_footer_and_canhoto_stack_at_page_bottom():
    footer = next(b for b in PAGE1_BLOCKS if b.name == "rodape")
    canhoto = next(b for b in PAGE1_BLOCKS if b.name == "canhoto")
    assert footer.top_mm == FOOTER_INFO_TOP
    assert canhoto.top_mm == footer.top_mm + footer.height_mm + CANHOTO_CUT_LINE_GAP_MM
    assert CANHOTO_BOTTOM_TOP == canhoto.top_mm
    assert canhoto.top_mm + canhoto.height_mm + PAGE_BOTTOM_MARGIN_MM == A4_PORTRAIT.height_mm


def test_canhoto_height_moc_range():
    assert 15 <= CANHOTO_HEIGHT <= 20


def test_nfe_strip_two_rows_meets_dest():
    strip = next(b for b in PAGE1_BLOCKS if b.name == "nfe_strip")
    dest = next(b for b in PAGE1_BLOCKS if b.name == "destinatario")
    assert strip.height_mm == 17.0
    assert dest.top_mm == block_bottom_mm(strip)


def test_header_columns_sum_to_content_width():
    from integrations.sefaz_nfe.danfe.layout import (
        HEADER_BARCODE_WIDTH_MM,
        HEADER_DANFE_WIDTH_MM,
        HEADER_EMIT_WIDTH_MM,
    )

    total = HEADER_EMIT_WIDTH_MM + HEADER_DANFE_WIDTH_MM + HEADER_BARCODE_WIDTH_MM
    assert abs(total - content_width_mm()) <= 0.5


def test_key_block_tops_match_construforti_page_top():
    from integrations.sefaz_nfe.danfe.layout import PAGE_TOP_MM, _LAYOUT_UPLIFT_MM

    assert PAGE_TOP_MM == 8.0
    assert HEADER_TOP == PAGE_TOP_MM
    assert DEST_TOP == 81.6 - _LAYOUT_UPLIFT_MM
    assert BILLING_TOP == 111.3 - _LAYOUT_UPLIFT_MM
    assert TAX_TOP == 127.8 - _LAYOUT_UPLIFT_MM
    assert TRANSPORT_TOP == 149.0 - _LAYOUT_UPLIFT_MM
    assert PAGE1_ITEMS_HEADER_TOP == 182.9 - _LAYOUT_UPLIFT_MM
    assert ISSQN_TOP == 239.0
    assert FOOTER_INFO_TOP == ISSQN_TOP + 8.5 + 0.5
