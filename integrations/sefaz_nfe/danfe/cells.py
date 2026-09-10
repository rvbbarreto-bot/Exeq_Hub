"""Desenho de celulas MOC — rotulo (topo) + valor (corpo)."""

from __future__ import annotations

from integrations.sefaz_nfe.danfe.formatters import danfe_upper
from integrations.sefaz_nfe.danfe.layout import (
    FONT_BLOCK_TITLE,
    FONT_TABLE_BODY,
    STROKE_PT,
    mm_to_pt,
    y_top,
)


def _fit_text(c, text: str, font: str, size: float, max_w_pt: float) -> str:
    out = danfe_upper(text or "—")
    while out and c.stringWidth(out, font, size) > max_w_pt:
        out = out[:-1]
    return out


def draw_cell(
    c,
    *,
    left_pt: float,
    top_mm: float,
    width_mm: float,
    height_mm: float,
    page_h: float,
    label: str,
    value: str,
    fonts: dict[str, str],
    label_pt: float = FONT_BLOCK_TITLE,
    value_pt: float = FONT_TABLE_BODY,
    value_bold: bool = False,
    value_align: str = "left",
) -> None:
    top_y = y_top(page_h, top_mm)
    h_pt = mm_to_pt(height_mm)
    w_pt = mm_to_pt(width_mm)
    c.setLineWidth(STROKE_PT)
    c.rect(left_pt, top_y - h_pt, w_pt, h_pt)
    pad = mm_to_pt(0.8)
    inner_w = max(w_pt - pad * 2, mm_to_pt(2))
    if label:
        c.setFont(fonts["bold"], label_pt)
        label_y = top_y - mm_to_pt(2.8)
        c.drawString(left_pt + pad, label_y, _fit_text(c, label, fonts["bold"], label_pt, inner_w))
    font = fonts["bold"] if value_bold else fonts["body"]
    c.setFont(font, value_pt)
    value_offset = min(6.2 if label else 4.5, max(height_mm - 2.0, 3.5))
    value_y = top_y - mm_to_pt(value_offset)
    text = _fit_text(c, value or "—", font, value_pt, inner_w)
    if value_align == "right":
        c.drawRightString(left_pt + w_pt - pad, value_y, text)
    else:
        c.drawString(left_pt + pad, value_y, text)


def draw_section_band(
    c,
    *,
    left_pt: float,
    top_mm: float,
    width_mm: float,
    page_h: float,
    title: str,
    fonts: dict[str, str],
    height_mm: float = 4.2,
) -> None:
    top_y = y_top(page_h, top_mm)
    c.setLineWidth(STROKE_PT)
    c.line(left_pt, top_y, left_pt + mm_to_pt(width_mm), top_y)
    if title:
        c.setFont(fonts["bold"], FONT_BLOCK_TITLE)
        c.drawString(left_pt + mm_to_pt(0.8), top_y - mm_to_pt(3.2), title.upper())


def draw_cells_row(
    c,
    *,
    left_pt: float,
    top_mm: float,
    page_h: float,
    cells: list[tuple[float, str, str]],
    fonts: dict[str, str],
    height_mm: float = 8.5,
    value_bold_last: bool = False,
    value_align_right_from: int | None = None,
) -> None:
    x_mm = 0.0
    for idx, (width_mm, label, value) in enumerate(cells):
        align_right = value_align_right_from is not None and idx >= value_align_right_from
        draw_cell(
            c,
            left_pt=left_pt + mm_to_pt(x_mm),
            top_mm=top_mm,
            width_mm=width_mm,
            height_mm=height_mm,
            page_h=page_h,
            label=label,
            value=value,
            fonts=fonts,
            value_bold=value_bold_last and idx == len(cells) - 1,
            value_align="right" if align_right else "left",
        )
        x_mm += width_mm


def draw_vline(
    c,
    *,
    left_pt: float,
    x_mm: float,
    top_mm: float,
    bottom_mm: float,
    page_h: float,
) -> None:
    x_pt = left_pt + mm_to_pt(x_mm)
    c.line(x_pt, y_top(page_h, top_mm), x_pt, y_top(page_h, bottom_mm))
