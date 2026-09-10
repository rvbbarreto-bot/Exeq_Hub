"""Especificacao geometrica A4 Retrato — MOC Anexo II v7.00 secao 3.8.1 (cm -> mm)."""

from __future__ import annotations

from dataclasses import dataclass

MM = 72 / 25.4  # pt por mm


@dataclass(frozen=True)
class PageSpec:
    width_mm: float = 210.0
    height_mm: float = 297.0
    orientation: str = "portrait"

    @property
    def width_pt(self) -> float:
        return self.width_mm * MM

    @property
    def height_pt(self) -> float:
        return self.height_mm * MM


@dataclass(frozen=True)
class BlockSpec:
    name: str
    top_mm: float
    height_mm: float
    moc_section: str = ""


A4_PORTRAIT = PageSpec()

# MOC 3.6.2 — margem lateral minima 0,25 cm
MARGIN_LEFT_MM = 2.5
MARGIN_RIGHT_MM = 2.5
STROKE_PT = 0.5

# Canhoto no rodape (padrao UniDANFE / refs ERP) — MOC 3.3.1
CANHOTO_POSITION = "bottom"

# Topo folha — CONSTRUFORTI NF 3925 ~8 mm (MOC padrão 25,4 mm)
PAGE_TOP_MM = 8.0
_LAYOUT_UPLIFT_MM = 25.4 - PAGE_TOP_MM

# Cabecalho — quadros emitente + DANFE + barcode (alt 3,92 cm)
HEADER_TOP = PAGE_TOP_MM
HEADER_HEIGHT = 39.2
# CONSTRUFORTI NF 3925 — emit ~85,5 / DANFE ~28,6 / chave ~90,9 mm (área útil 205 mm)
HEADER_EMIT_WIDTH_MM = 85.5
HEADER_DANFE_WIDTH_MM = 28.6
HEADER_BARCODE_WIDTH_MM = 210.0 - MARGIN_LEFT_MM - MARGIN_RIGHT_MM - HEADER_EMIT_WIDTH_MM - HEADER_DANFE_WIDTH_MM

# Faixa natureza + protocolo + IE/CNPJ emitente (2 linhas)
NFE_STRIP_TOP = 64.6 - _LAYOUT_UPLIFT_MM
NFE_STRIP_HEIGHT = 17.0

# Destinatario
DEST_TOP = 81.6 - _LAYOUT_UPLIFT_MM
DEST_HEIGHT = 29.7

# Fatura — faixa título 4,2 + linha 8,5
BILLING_TOP = 111.3 - _LAYOUT_UPLIFT_MM
BILLING_HEIGHT = 12.7

# Imposto — 2 linhas
TAX_TOP = 127.8 - _LAYOUT_UPLIFT_MM
TAX_HEIGHT = 14.5

# Transporte — 3 linhas + faixa título
TRANSPORT_TOP = 149.0 - _LAYOUT_UPLIFT_MM
TRANSPORT_HEIGHT = 29.7

# Produtos — topo sobe; base fixa (rodape/canhoto no fim da folha)
PAGE1_ITEMS_HEADER_TOP = 182.9 - _LAYOUT_UPLIFT_MM
ITEMS_HEADER_HEIGHT = 8.5
ITEMS_AREA_BOTTOM = 247.0

# ISSQN — acima do rodape (sobe p/ absorver vazio visual da grade)
FOOTER_BLOCK_UPLIFT_MM = 8.0
ISSQN_TOP = ITEMS_AREA_BOTTOM - FOOTER_BLOCK_UPLIFT_MM
ISSQN_HEIGHT = 8.5
ISSQN_FOOTER_GAP_MM = 0.5

# Rodape dados adicionais + canhoto (UniDANFE / CONSTRUFORTI)
FOOTER_INFO_SPLIT_RATIO = 0.68
FOOTER_CONTENT_HEIGHT = 22.0
FOOTER_TECH_STRIP_HEIGHT = 4.0
FOOTER_INFO_HEIGHT = FOOTER_CONTENT_HEIGHT + FOOTER_TECH_STRIP_HEIGHT
FOOTER_INFO_TOP = ISSQN_TOP + ISSQN_HEIGHT + ISSQN_FOOTER_GAP_MM
CANHOTO_CUT_LINE_GAP_MM = 2.0
CANHOTO_HEIGHT = 20.0
CANHOTO_BOTTOM_TOP = FOOTER_INFO_TOP + FOOTER_INFO_HEIGHT + CANHOTO_CUT_LINE_GAP_MM
PAGE_BOTTOM_MARGIN_MM = A4_PORTRAIT.height_mm - CANHOTO_BOTTOM_TOP - CANHOTO_HEIGHT
CANHOTO_NF_BOX_WIDTH_MM = 26.0
CANHOTO_DATE_WIDTH_MM = 34.0
CANHOTO_SIGNATURE_ROW_HEIGHT = 6.5
CANHOTO_RECEIPT_LINE_SPACING_MM = 2.9


def footer_info_top_mm(*, has_delivery: bool = False) -> float:
    return page1_offsets(has_delivery=has_delivery).issqn_top + ISSQN_HEIGHT + ISSQN_FOOTER_GAP_MM

# Folha 2+ — cabecalho repetido, grid apos header
CONT_ITEMS_HEADER_TOP = HEADER_TOP + HEADER_HEIGHT + 1.0

BARCODE_BAR_HEIGHT_MM = 13.0
BARCODE_QUIET_MM = 2.0

# MOC 3.7 — tipografia minima (pt)
FONT_DANFE_TITLE = 12
FONT_DANFE_SUBTITLE = 8
FONT_EMIT_NAME = 12
FONT_BODY = 8
FONT_BLOCK_TITLE = 6
FONT_TABLE_HEADER = 6
FONT_TABLE_BODY = 8
FONT_ACCESS_KEY = 8
FONT_FIELD_VALUE = 10

ITEMS_HEADER_TOP = PAGE1_ITEMS_HEADER_TOP

# 13 colunas — calibradas CONSTRUFORTI NF 3925 (2.6-spec, area util ~205 mm)
ITEM_COL_WIDTHS_MM: tuple[float, ...] = (
    12.7,
    84.0,
    12.7,
    9.2,
    7.8,
    7.8,
    10.0,
    9.8,
    9.6,
    10.2,
    9.8,
    7.9,
    13.5,
)

# Larguras de células por bloco (mm) — calibradas CONSTRUFORTI NF 3925 (2.7-spec)
from integrations.sefaz_nfe.danfe.calibrate import (
    DELIVERY_ROW1_WIDTHS_CONSTRUFORTI_MM,
    DELIVERY_ROW2_WIDTHS_CONSTRUFORTI_MM,
    DEST_ROW1_WIDTHS_CONSTRUFORTI_MM,
    DEST_ROW2_WIDTHS_CONSTRUFORTI_MM,
    DEST_ROW3_WIDTHS_CONSTRUFORTI_MM,
    TAX_ROW1_WIDTHS_CONSTRUFORTI_MM,
    TAX_ROW2_WIDTHS_CONSTRUFORTI_MM,
    TRANSPORT_ROW1_WIDTHS_CONSTRUFORTI_MM,
    TRANSPORT_ROW2_WIDTHS_CONSTRUFORTI_MM,
    TRANSPORT_ROW3_WIDTHS_CONSTRUFORTI_MM,
)

DEST_ROW1_WIDTHS_MM = DEST_ROW1_WIDTHS_CONSTRUFORTI_MM
DEST_ROW2_WIDTHS_MM = DEST_ROW2_WIDTHS_CONSTRUFORTI_MM
DEST_ROW3_WIDTHS_MM = DEST_ROW3_WIDTHS_CONSTRUFORTI_MM
DELIVERY_ROW1_WIDTHS_MM = DELIVERY_ROW1_WIDTHS_CONSTRUFORTI_MM
DELIVERY_ROW2_WIDTHS_MM = DELIVERY_ROW2_WIDTHS_CONSTRUFORTI_MM
TAX_ROW1_WIDTHS_MM = TAX_ROW1_WIDTHS_CONSTRUFORTI_MM
TAX_ROW2_WIDTHS_MM = TAX_ROW2_WIDTHS_CONSTRUFORTI_MM
TRANSPORT_ROW1_WIDTHS_MM = TRANSPORT_ROW1_WIDTHS_CONSTRUFORTI_MM
TRANSPORT_ROW2_WIDTHS_MM = TRANSPORT_ROW2_WIDTHS_CONSTRUFORTI_MM
TRANSPORT_ROW3_WIDTHS_MM = TRANSPORT_ROW3_WIDTHS_CONSTRUFORTI_MM

# Local de entrega — 2 linhas de campos (NT 2018.005)
DELIVERY_BLOCK_HEIGHT = 21.2


@dataclass(frozen=True)
class Page1Offsets:
    delivery_top: float | None
    billing_top: float
    tax_top: float
    transport_top: float
    items_header_top: float
    items_area_bottom: float
    issqn_top: float


def page1_offsets(*, has_delivery: bool) -> Page1Offsets:
    shift = DELIVERY_BLOCK_HEIGHT if has_delivery else 0.0
    items_bottom = ITEMS_AREA_BOTTOM - shift
    return Page1Offsets(
        delivery_top=DEST_TOP + DEST_HEIGHT if has_delivery else None,
        billing_top=BILLING_TOP + shift,
        tax_top=TAX_TOP + shift,
        transport_top=TRANSPORT_TOP + shift,
        items_header_top=PAGE1_ITEMS_HEADER_TOP + shift,
        items_area_bottom=items_bottom,
        issqn_top=items_bottom - FOOTER_BLOCK_UPLIFT_MM,
    )

PAGE1_BLOCKS: tuple[BlockSpec, ...] = (
    BlockSpec("header", HEADER_TOP, HEADER_HEIGHT, "MOC-II"),
    BlockSpec("nfe_strip", NFE_STRIP_TOP, NFE_STRIP_HEIGHT, "MOC-IIb"),
    BlockSpec("destinatario", DEST_TOP, DEST_HEIGHT, "MOC-III"),
    BlockSpec("fatura", BILLING_TOP, BILLING_HEIGHT, "MOC-IV"),
    BlockSpec("imposto", TAX_TOP, TAX_HEIGHT, "MOC-V"),
    BlockSpec("transporte", TRANSPORT_TOP, TRANSPORT_HEIGHT, "MOC-VI"),
    BlockSpec("produtos", PAGE1_ITEMS_HEADER_TOP, ITEMS_HEADER_HEIGHT, "MOC-VIII"),
    BlockSpec("issqn", ISSQN_TOP, ISSQN_HEIGHT, "MOC-VII"),
    BlockSpec("rodape", FOOTER_INFO_TOP, FOOTER_INFO_HEIGHT, "MOC-IX"),
    BlockSpec("canhoto", CANHOTO_BOTTOM_TOP, CANHOTO_HEIGHT, "MOC-I"),
)


def mm_to_pt(mm: float) -> float:
    return mm * MM


def y_top(page_h_pt: float, top_mm: float) -> float:
    return page_h_pt - mm_to_pt(top_mm)


def content_width_mm(page: PageSpec = A4_PORTRAIT) -> float:
    return page.width_mm - MARGIN_LEFT_MM - MARGIN_RIGHT_MM


def block_bottom_mm(block: BlockSpec) -> float:
    return block.top_mm + block.height_mm


def items_area_top_mm(*, continuation: bool, has_delivery: bool = False) -> float:
    if continuation:
        return CONT_ITEMS_HEADER_TOP + ITEMS_HEADER_HEIGHT
    return page1_offsets(has_delivery=has_delivery).items_header_top + ITEMS_HEADER_HEIGHT


def items_area_bottom_mm(*, has_delivery: bool = False) -> float:
    return page1_offsets(has_delivery=has_delivery).items_area_bottom


def item_column_offsets_mm() -> list[float]:
    bounds = [0.0]
    for width in ITEM_COL_WIDTHS_MM:
        bounds.append(bounds[-1] + width)
    return bounds


def verify_page1_layout_stack() -> list[str]:
    errors: list[str] = []
    ordered = [b for b in PAGE1_BLOCKS if b.name not in {"rodape", "produtos", "canhoto"}]
    for prev, nxt in zip(ordered, ordered[1:]):
        gap = nxt.top_mm - block_bottom_mm(prev)
        if gap < -0.5:
            errors.append(f"sobreposicao {prev.name}/{nxt.name}: gap={gap:.2f}mm")
    footer = next(b for b in PAGE1_BLOCKS if b.name == "rodape")
    if footer.top_mm + footer.height_mm > A4_PORTRAIT.height_mm + 0.5:
        errors.append("rodape excede A4")
    canhoto = next(b for b in PAGE1_BLOCKS if b.name == "canhoto")
    if canhoto.top_mm + canhoto.height_mm > A4_PORTRAIT.height_mm + 0.5:
        errors.append("canhoto excede A4")
    return errors
