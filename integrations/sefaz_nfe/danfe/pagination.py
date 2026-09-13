"""Paginação determinística — itens + overflow infCpl (Fase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field

from integrations.sefaz_nfe.danfe.formatters import format_approx_trib_percent, format_money_br, wrap_text
from integrations.sefaz_nfe.danfe.layout import (
    HEADER_HEIGHT,
    HEADER_TOP,
    items_area_bottom_mm,
    items_area_top_mm,
    mm_to_pt,
    page1_offsets,
)
from integrations.sefaz_nfe.danfe.viewmodel import DanfeViewModel

ROW_HEIGHT_MM = 4.25
DESC_MAX_CHARS = 42
FOOTER_CPL_MAX_LINES = 6
FOOTER_FISCO_MAX_LINES = 4
INF_CPL_WRAP = 58


@dataclass
class ItemRowPlan:
    item_index: int
    lines: list[str]
    height_mm: float


@dataclass
class PagePlan:
    page_index: int
    item_rows: list[ItemRowPlan]
    show_canhoto: bool
    show_full_header: bool
    show_continuation_header: bool
    show_transport: bool
    show_tax: bool
    show_billing: bool
    show_delivery: bool
    show_footer_info: bool
    footer_inf_cpl_lines: list[str] = field(default_factory=list)
    footer_fisco_lines: list[str] = field(default_factory=list)
    inf_cpl_continuation: bool = False

    @property
    def items_header_top_mm(self) -> float:
        if self.show_continuation_header:
            return HEADER_TOP + HEADER_HEIGHT + 1.0
        return page1_offsets(has_delivery=self.show_delivery).items_header_top


def _item_description_lines(item) -> list[str]:
    lines = wrap_text(item.description, max_chars=DESC_MAX_CHARS)
    if item.ean:
        lines.append(f"Cód. Barras: {item.ean}")
    return lines


def _row_plans(vm: DanfeViewModel) -> list[ItemRowPlan]:
    plans: list[ItemRowPlan] = []
    for idx, item in enumerate(vm.items):
        lines = _item_description_lines(item)
        height = max(ROW_HEIGHT_MM, len(lines) * (ROW_HEIGHT_MM * 0.85))
        plans.append(ItemRowPlan(item_index=idx, lines=lines, height_mm=height))
    return plans


def inf_cpl_display_text(vm: DanfeViewModel) -> str:
    return _inf_cpl_source(vm)


def _inf_cpl_source(vm: DanfeViewModel) -> str:
    parts: list[str] = []
    trib = (vm.totals.approx_taxes or "").strip()
    if trib and trib not in ("0", "0.00", "0,00"):
        pct = format_approx_trib_percent(trib, vm.totals.total_nf)
        trib_line = f"VALOR APROXIMADO DOS TRIBUTOS R$ {format_money_br(trib)}"
        if pct:
            trib_line = f"{trib_line} {pct}"
        parts.append(trib_line)
    if vm.inf_cpl:
        parts.append(vm.inf_cpl)
    return " ".join(parts)


def _append_inf_cpl_overflow_pages(
    pages: list[PagePlan],
    *,
    cpl_lines: list[str],
    fisco_lines: list[str],
) -> None:
    if not pages:
        return
    last = pages[-1]
    last.show_footer_info = True
    last.footer_inf_cpl_lines = cpl_lines[:FOOTER_CPL_MAX_LINES]
    last.footer_fisco_lines = fisco_lines[:FOOTER_FISCO_MAX_LINES]
    rest = cpl_lines[FOOTER_CPL_MAX_LINES:]
    page_idx = len(pages)
    while rest:
        pages.append(
            PagePlan(
                page_index=page_idx,
                item_rows=[],
                show_canhoto=False,
                show_full_header=False,
                show_continuation_header=True,
                show_transport=False,
                show_tax=False,
                show_billing=False,
                show_delivery=False,
                show_footer_info=True,
                footer_inf_cpl_lines=rest[:FOOTER_CPL_MAX_LINES],
                footer_fisco_lines=[],
                inf_cpl_continuation=True,
            )
        )
        rest = rest[FOOTER_CPL_MAX_LINES:]
        page_idx += 1


def plan_pages(vm: DanfeViewModel) -> list[PagePlan]:
    has_delivery = vm.delivery_differs_from_dest
    rows = _row_plans(vm)
    area_bottom = items_area_bottom_mm(has_delivery=has_delivery)
    first_page_capacity = area_bottom - items_area_top_mm(continuation=False, has_delivery=has_delivery) - 2.0
    cont_page_capacity = area_bottom - items_area_top_mm(continuation=True) - 2.0

    pages: list[PagePlan] = []
    remaining = list(rows)
    page_idx = 0
    while remaining or page_idx == 0:
        capacity = first_page_capacity if page_idx == 0 else cont_page_capacity
        used = 0.0
        page_rows: list[ItemRowPlan] = []
        while remaining and used + remaining[0].height_mm <= capacity:
            row = remaining.pop(0)
            page_rows.append(row)
            used += row.height_mm
        pages.append(
            PagePlan(
                page_index=page_idx,
                item_rows=page_rows,
                show_canhoto=page_idx == 0,
                show_full_header=page_idx == 0,
                show_continuation_header=page_idx > 0,
                show_transport=page_idx == 0,
                show_tax=page_idx == 0,
                show_billing=page_idx == 0 and bool(vm.duplicates or vm.invoice_number_fat),
                show_delivery=page_idx == 0 and has_delivery,
                show_footer_info=False,
            )
        )
        page_idx += 1
        if not remaining:
            break
        if page_idx > 50:
            break

    cpl_lines = wrap_text(_inf_cpl_source(vm), max_chars=INF_CPL_WRAP)
    fisco_lines = wrap_text(vm.inf_ad_fisco, max_chars=INF_CPL_WRAP)
    _append_inf_cpl_overflow_pages(pages, cpl_lines=cpl_lines, fisco_lines=fisco_lines)
    return pages


def row_height_pt() -> float:
    return mm_to_pt(ROW_HEIGHT_MM)
