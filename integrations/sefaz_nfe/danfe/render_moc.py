"""DANFE Modelo 55 Retrato — renderer MOC Fase D (camada B)."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from reportlab.lib.colors import black, red
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from integrations.sefaz_nfe.danfe.barcode import access_key_barcode_drawing
from integrations.sefaz_nfe.danfe.formatters import (
    danfe_upper,
    format_access_key,
    format_cep,
    format_date_br,
    format_datetime_br,
    format_document,
    format_money_br,
    format_nf_number,
    format_phone_br,
    format_qty,
    format_rate_br,
    format_time_br,
    format_unit_price,
    format_weight_br,
)
from integrations.sefaz_nfe.danfe.cells import _fit_text, draw_cell, draw_cells_row, draw_section_band, draw_vline
from integrations.sefaz_nfe.danfe.layout import (
    A4_PORTRAIT,
    BARCODE_BAR_HEIGHT_MM,
    BILLING_HEIGHT,
    CANHOTO_BOTTOM_TOP,
    CANHOTO_DATE_WIDTH_MM,
    CANHOTO_HEIGHT,
    CANHOTO_NF_BOX_WIDTH_MM,
    CANHOTO_POSITION,
    CANHOTO_RECEIPT_LINE_SPACING_MM,
    CANHOTO_SIGNATURE_ROW_HEIGHT,
    FOOTER_CONTENT_HEIGHT,
    FOOTER_INFO_SPLIT_RATIO,
    FOOTER_TECH_STRIP_HEIGHT,
    DELIVERY_BLOCK_HEIGHT,
    DELIVERY_ROW1_WIDTHS_MM,
    DELIVERY_ROW2_WIDTHS_MM,
    DEST_HEIGHT,
    DEST_ROW1_WIDTHS_MM,
    DEST_ROW2_WIDTHS_MM,
    DEST_ROW3_WIDTHS_MM,
    DEST_TOP,
    FONT_ACCESS_KEY,
    FONT_BLOCK_TITLE,
    FONT_BODY,
    FONT_DANFE_SUBTITLE,
    FONT_DANFE_TITLE,
    FONT_EMIT_NAME,
    FONT_FIELD_VALUE,
    FONT_TABLE_BODY,
    FONT_TABLE_HEADER,
    FOOTER_INFO_HEIGHT,
    footer_info_top_mm,
    HEADER_DANFE_WIDTH_MM,
    HEADER_EMIT_WIDTH_MM,
    HEADER_HEIGHT,
    HEADER_TOP,
    ISSQN_HEIGHT,
    ITEMS_HEADER_HEIGHT,
    MARGIN_LEFT_MM,
    NFE_STRIP_HEIGHT,
    NFE_STRIP_TOP,
    Page1Offsets,
    TAX_HEIGHT,
    TAX_ROW1_WIDTHS_MM,
    TAX_ROW2_WIDTHS_MM,
    TRANSPORT_HEIGHT,
    TRANSPORT_ROW1_WIDTHS_MM,
    TRANSPORT_ROW2_WIDTHS_MM,
    TRANSPORT_ROW3_WIDTHS_MM,
    content_width_mm,
    item_column_offsets_mm,
    mm_to_pt,
    page1_offsets,
    STROKE_PT,
    y_top,
)
from integrations.sefaz_nfe.danfe.pagination import plan_pages
from integrations.sefaz_nfe.danfe.viewmodel import DanfeViewModel, build_danfe_viewmodel

LAYOUT_VERSION = "exeq-danfe-2.7.7-spec"


def _is_simples_nacional(vm: DanfeViewModel) -> bool:
    return vm.emit_crt in {"1", "2", "3"}


def _tax_col_label(vm: DanfeViewModel) -> str:
    return "CSOSN" if _is_simples_nacional(vm) else "CST"


def _tax_code_display(item, vm: DanfeViewModel) -> str:
    tc = item.tax_classification
    if not tc.code:
        return ""
    if _is_simples_nacional(vm) and tc.kind == "CSOSN":
        return tc.code.zfill(4)
    return tc.code.zfill(2)


@lru_cache(maxsize=1)
def _fonts() -> dict[str, str]:
    title, body, body_b = "Helvetica-Bold", "Helvetica", "Helvetica-Bold"
    for regular, bold in (
        (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ):
        try:
            if regular.is_file() and bold.is_file():
                pdfmetrics.registerFont(TTFont("DanfeReg", str(regular)))
                pdfmetrics.registerFont(TTFont("DanfeBold", str(bold)))
                return {"title": "DanfeBold", "body": "DanfeReg", "bold": "DanfeBold"}
        except Exception:  # noqa: BLE001
            continue
    return {"title": title, "body": body, "bold": body_b}


def render_danfe_moc_pdf(
    xml_bytes: bytes,
    *,
    cancelled: bool = False,
    logo_bytes: bytes | None = None,
) -> bytes:
    vm = build_danfe_viewmodel(xml_bytes, cancelled=cancelled)
    if logo_bytes:
        vm.logo_bytes = logo_bytes
    pages = plan_pages(vm)
    total_pages = max(1, len(pages))
    fonts = _fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setTitle(f"DANFE {vm.series}/{vm.number}")
    c.setSubject(f"danfe_layout_version={LAYOUT_VERSION}")
    c.setCreator("EXEQ Hub")

    for idx, plan in enumerate(pages):
        page_no = plan.page_index + 1
        _draw_page(
            c,
            vm=vm,
            plan=plan,
            page_no=page_no,
            total_pages=total_pages,
            fonts=fonts,
            page_w=w,
            page_h=h,
        )
        if idx < len(pages) - 1:
            c.showPage()
    c.save()
    return buf.getvalue()


def _draw_page(
    c: canvas.Canvas,
    *,
    vm: DanfeViewModel,
    plan,
    page_no: int,
    total_pages: int,
    fonts: dict[str, str],
    page_w: float,
    page_h: float,
) -> None:
    c.setStrokeColor(black)
    c.setLineWidth(STROKE_PT)
    left = mm_to_pt(MARGIN_LEFT_MM)
    width = mm_to_pt(content_width_mm())

    if vm.cancelled:
        _watermark_cancelled(c, page_w, page_h, fonts)
    if vm.tp_amb == "2":
        _watermark_homolog(c, page_w, page_h, fonts)

    if plan.show_full_header or plan.show_continuation_header:
        _draw_identification_header(c, vm, fonts, left, width, page_h, page_no, total_pages)

    if page_no == 1:
        offs = page1_offsets(has_delivery=plan.show_delivery)
        _draw_nfe_strip(c, vm, fonts, left, page_h)
        _draw_dest(c, vm, fonts, left, page_h)
        if plan.show_delivery:
            _draw_delivery(c, vm, fonts, left, page_h, offs)
        if plan.show_billing:
            _draw_billing(c, vm, fonts, left, page_h, offs)
        if plan.show_tax:
            _draw_tax_totals(c, vm, fonts, left, page_h, offs)
        if plan.show_transport:
            _draw_transport(c, vm, fonts, left, page_h, offs)

    if plan.item_rows:
        items_top = plan.items_header_top_mm
        _draw_items(c, vm, plan, fonts, left, width, page_h, items_header_top_mm=items_top)

    if page_no == 1 and plan.show_tax:
        _draw_issqn(c, vm, fonts, left, page_h, page1_offsets(has_delivery=plan.show_delivery))

    if plan.show_footer_info:
        _draw_additional_info(c, vm, plan, fonts, left, width, page_h)

    if plan.show_canhoto and CANHOTO_POSITION == "bottom":
        _draw_canhoto_bottom(c, vm, fonts, left, width, page_h, page_no, total_pages)


def _rect_mm(c, left_pt: float, top_mm: float, width_pt: float, height_mm: float, page_h: float) -> None:
    top_y = y_top(page_h, top_mm)
    c.rect(left_pt, top_y - mm_to_pt(height_mm), width_pt, mm_to_pt(height_mm))


def _hline_mm(c, left_pt: float, top_mm: float, width_pt: float, page_h: float) -> None:
    y = y_top(page_h, top_mm)
    c.line(left_pt, y, left_pt + width_pt, y)


def _draw_centred_fit(
    c,
    cx: float,
    y: float,
    text: str,
    font: str,
    size: float,
    max_w_pt: float,
) -> None:
    c.drawCentredString(cx, y, _fit_text(c, text, font, size, max_w_pt))


def _draw_tp_nf_boxes(
    c,
    *,
    danfe_left_pt: float,
    danfe_w_mm: float,
    y: float,
    tp_nf: str,
    fonts: dict[str, str],
) -> float:
    """Indicador 0-Entrada / 1-Saída com caixa quadrada no dígito ativo (UniDANFE)."""
    box = mm_to_pt(4.0)
    spacing = mm_to_pt(3.5)
    pair_w = box * 2 + spacing
    danfe_w_pt = mm_to_pt(danfe_w_mm)
    label_w = box + mm_to_pt(1.0)
    start_x = danfe_left_pt + (danfe_w_pt - pair_w) / 2
    active = "1" if tp_nf == "1" else "0"
    label_pt = 5.5
    for idx, (digit, label) in enumerate((("0", "ENTRADA"), ("1", "SAIDA"))):
        bx = start_x + idx * (box + spacing)
        by = y - box
        is_active = digit == active
        c.setLineWidth(1.4 if is_active else STROKE_PT)
        c.rect(bx, by, box, box)
        c.setFont(fonts["bold"] if is_active else fonts["body"], FONT_FIELD_VALUE if is_active else FONT_BODY)
        c.drawCentredString(bx + box / 2, by + mm_to_pt(1.0), digit)
        c.setFont(fonts["body"], label_pt)
        _draw_centred_fit(c, bx + box / 2, by - mm_to_pt(2.4), label, fonts["body"], label_pt, label_w)
    c.setLineWidth(STROKE_PT)
    return y - mm_to_pt(9.5)


def _draw_dashed_cut_line(c, left, width, page_h, top_mm: float) -> None:
    y = y_top(page_h, top_mm)
    dash = mm_to_pt(4)
    gap = mm_to_pt(2.5)
    x = left
    while x < left + width:
        x_end = min(x + dash, left + width)
        c.line(x, y, x_end, y)
        x += dash + gap


def _draw_canhoto_bottom(c, vm, fonts, left, width, page_h, page_no, total_pages) -> None:
    top = CANHOTO_BOTTOM_TOP
    _draw_dashed_cut_line(c, left, width, page_h, top - 0.3)

    nf_w = mm_to_pt(CANHOTO_NF_BOX_WIDTH_MM)
    main_w = width - nf_w
    sig_h = mm_to_pt(CANHOTO_SIGNATURE_ROW_HEIGHT)
    top_y = y_top(page_h, top)
    h_pt = mm_to_pt(CANHOTO_HEIGHT)
    bottom_y = top_y - h_pt
    sig_top_y = bottom_y + sig_h
    date_w = mm_to_pt(CANHOTO_DATE_WIDTH_MM)

    c.setLineWidth(STROKE_PT)
    c.rect(left, bottom_y, width, h_pt)
    c.line(left + main_w, top_y, left + main_w, bottom_y)
    c.line(left, sig_top_y, left + main_w, sig_top_y)
    c.line(left + date_w, sig_top_y, left + date_w, bottom_y)

    nf_cx = left + main_w + nf_w / 2
    c.setFont(fonts["bold"], FONT_BLOCK_TITLE)
    c.drawCentredString(nf_cx, top_y - mm_to_pt(4.2), "NF-e")
    c.setFont(fonts["bold"], 14)
    c.drawCentredString(nf_cx, top_y - mm_to_pt(10.5), format_nf_number(vm.number))
    c.setFont(fonts["body"], FONT_BODY)
    c.drawCentredString(nf_cx, top_y - mm_to_pt(15.5), f"SERIE {vm.series}")

    emit = danfe_upper(vm.emit_name or "—")
    dest = danfe_upper(vm.dest_name or "—")
    dest_addr = danfe_upper(vm.dest_address or "—")
    receipt = (
        f"RECEBEMOS DE {emit} OS PRODUTOS E/OU SERVICOS CONSTANTES DA NOTA FISCAL ELETRONICA "
        f"N. {format_nf_number(vm.number)}. EMISSAO: {format_date_br(vm.issue_date)} "
        f"VALOR TOTAL: {format_money_br(vm.totals.total_nf)} "
        f"DESTINATARIO: {dest} - {dest_addr}"
    )
    text_pad = mm_to_pt(1.5)
    text_max = main_w - text_pad * 2
    line_step = mm_to_pt(CANHOTO_RECEIPT_LINE_SPACING_MM)
    c.setFont(fonts["body"], FONT_BODY)
    y_text = top_y - mm_to_pt(2.8)
    for line in _wrap_lines(receipt, 92)[:4]:
        clipped = _fit_text(c, line, fonts["body"], FONT_BODY, text_max)
        c.drawString(left + text_pad, y_text, clipped)
        y_text -= line_step

    label_pad = mm_to_pt(1.2)
    label_y = sig_top_y - mm_to_pt(2.5)
    c.setFont(fonts["bold"], FONT_BLOCK_TITLE)
    c.drawString(
        left + label_pad,
        label_y,
        _fit_text(c, "DATA DO RECEBIMENTO", fonts["bold"], FONT_BLOCK_TITLE, date_w - label_pad * 2),
    )
    c.drawString(
        left + date_w + label_pad,
        label_y,
        _fit_text(
            c,
            "IDENTIFICACAO E ASSINATURA DO RECEBEDOR",
            fonts["bold"],
            FONT_BLOCK_TITLE,
            main_w - date_w - label_pad * 2,
        ),
    )


def _draw_identification_header(c, vm, fonts, left, width, page_h, page_no, total_pages) -> None:
    """Cabecalho MOC 3.8.1 — 3 colunas + divisores verticais."""
    _rect_mm(c, left, HEADER_TOP, width, HEADER_HEIGHT, page_h)
    w_mm = content_width_mm()
    emit_w = HEADER_EMIT_WIDTH_MM
    danfe_w = HEADER_DANFE_WIDTH_MM
    bc_w = w_mm - emit_w - danfe_w

    draw_vline(c, left_pt=left, x_mm=emit_w, top_mm=HEADER_TOP, bottom_mm=HEADER_TOP + HEADER_HEIGHT, page_h=page_h)
    draw_vline(
        c,
        left_pt=left,
        x_mm=emit_w + danfe_w,
        top_mm=HEADER_TOP,
        bottom_mm=HEADER_TOP + HEADER_HEIGHT,
        page_h=page_h,
    )

    emit_w_pt = mm_to_pt(emit_w)
    x0 = left + mm_to_pt(2)
    emit_inner_w = emit_w_pt - mm_to_pt(4)
    y_top_emit = y_top(page_h, HEADER_TOP + 2.5)
    y = y_top_emit
    if vm.logo_bytes:
        try:
            img = ImageReader(io.BytesIO(vm.logo_bytes))
            logo_h = mm_to_pt(14)
            logo_w = min(mm_to_pt(24), emit_inner_w * 0.75)
            logo_x = left + (emit_w_pt - logo_w) / 2
            c.drawImage(
                img,
                logo_x,
                y_top_emit - logo_h,
                width=logo_w,
                height=logo_h,
                preserveAspectRatio=True,
            )
            y = y_top_emit - logo_h - mm_to_pt(2)
        except Exception:  # noqa: BLE001
            pass
    c.setFont(fonts["bold"], FONT_BLOCK_TITLE)
    c.drawString(x0, y, _fit_text(c, "IDENTIFICAÇÃO DO EMITENTE", fonts["bold"], FONT_BLOCK_TITLE, emit_inner_w))
    y -= mm_to_pt(3.5)
    c.setFont(fonts["bold"], FONT_EMIT_NAME)
    c.drawString(x0, y, _fit_text(c, vm.emit_name or "—", fonts["bold"], FONT_EMIT_NAME, emit_inner_w))
    y -= mm_to_pt(3.8)
    c.setFont(fonts["body"], FONT_BODY)
    addr1 = vm.emit_address_line1 or vm.emit_address
    addr2 = vm.emit_address_line2
    for line in (addr1, addr2):
        if line:
            c.drawString(x0, y, _fit_text(c, line, fonts["body"], FONT_BODY, emit_inner_w))
            y -= mm_to_pt(3.0)
    if vm.emit_phone:
        c.drawString(x0, y, _fit_text(c, f"Fone/Fax: {format_phone_br(vm.emit_phone)}", fonts["body"], FONT_BODY, emit_inner_w))

    danfe_left = left + emit_w_pt
    danfe_w_pt = mm_to_pt(danfe_w)
    danfe_cx = danfe_left + danfe_w_pt / 2
    danfe_inner = danfe_w_pt - mm_to_pt(2)
    y = y_top(page_h, HEADER_TOP + 5)
    c.setFont(fonts["bold"], FONT_DANFE_TITLE)
    _draw_centred_fit(c, danfe_cx, y, "DANFE", fonts["bold"], FONT_DANFE_TITLE, danfe_inner)
    y -= mm_to_pt(4.5)
    sub_pt = 7.0
    c.setFont(fonts["body"], sub_pt)
    _draw_centred_fit(c, danfe_cx, y, "DOCUMENTO AUXILIAR DA", fonts["body"], sub_pt, danfe_inner)
    y -= mm_to_pt(3.0)
    _draw_centred_fit(c, danfe_cx, y, "NOTA FISCAL ELETRONICA", fonts["body"], sub_pt, danfe_inner)
    y -= mm_to_pt(4.0)
    y = _draw_tp_nf_boxes(
        c,
        danfe_left_pt=danfe_left,
        danfe_w_mm=danfe_w,
        y=y,
        tp_nf=vm.tp_nf,
        fonts=fonts,
    )
    y -= mm_to_pt(3.0)
    c.setFont(fonts["bold"], FONT_FIELD_VALUE)
    _draw_centred_fit(c, danfe_cx, y, f"N. {format_nf_number(vm.number)}", fonts["bold"], FONT_FIELD_VALUE, danfe_inner)
    y -= mm_to_pt(3.5)
    c.setFont(fonts["body"], FONT_BODY)
    _draw_centred_fit(
        c,
        danfe_cx,
        y,
        f"SERIE {vm.series}  FOLHA {page_no}/{total_pages}",
        fonts["body"],
        FONT_BODY,
        danfe_inner,
    )

    bc_left = left + emit_w_pt + danfe_w_pt + mm_to_pt(1.5)
    bc_w_pt = mm_to_pt(bc_w - 2.0)
    if vm.access_key and len("".join(ch for ch in vm.access_key if ch.isdigit())) == 44:
        y_bc = y_top(page_h, HEADER_TOP + 4.5)
        c.setFont(fonts["bold"], FONT_BLOCK_TITLE)
        c.drawString(bc_left, y_bc, "CHAVE DE ACESSO")
        y_bc -= mm_to_pt(3.2)
        c.setFont(fonts["bold"], FONT_ACCESS_KEY)
        key_text = format_access_key(vm.access_key)
        c.drawString(bc_left, y_bc, _fit_text(c, key_text, fonts["bold"], FONT_ACCESS_KEY, bc_w_pt))
        y_bc -= mm_to_pt(1.5)
        bc = access_key_barcode_drawing(vm.access_key, bar_height_mm=BARCODE_BAR_HEIGHT_MM)
        target_w = bc_w_pt
        if bc.width > 0:
            bc.scale(target_w / bc.width, 1.0)
        by = y_bc - bc.height
        bc.drawOn(c, bc_left, by)

    y = y_top(page_h, HEADER_TOP + HEADER_HEIGHT - 3.2)
    c.setFont(fonts["body"], FONT_BODY)
    if vm.authorization.is_contingency:
        c.drawString(bc_left, y, _fit_text(c, f"Emissao em contingencia ({vm.authorization.emission_mode})", fonts["body"], FONT_BODY, bc_w_pt))
        y -= mm_to_pt(3.0)
    c.drawString(bc_left, y, _fit_text(c, vm.consultation_hint, fonts["body"], FONT_BODY, bc_w_pt))


def _protocol_display(vm: DanfeViewModel) -> str:
    if vm.authorization.is_contingency:
        return f"Contingencia ({vm.authorization.emission_mode})"
    if vm.authorization.protocol:
        return (
            f"{vm.authorization.protocol}  {format_datetime_br(vm.authorization.authorized_at)}"
        )
    return "—"


def _draw_nfe_strip(c, vm, fonts, left, page_h) -> None:
    w = content_width_mm()
    draw_section_band(c, left_pt=left, top_mm=NFE_STRIP_TOP, width_mm=w, page_h=page_h, title="", fonts=fonts)
    row1 = NFE_STRIP_TOP + 0.5
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row1,
        page_h=page_h,
        fonts=fonts,
        cells=[
            (78.7, "NATUREZA DA OPERACAO", vm.nature or "—"),
            (126.3, "PROTOCOLO DE AUTORIZACAO DE USO", _protocol_display(vm)),
        ],
    )
    row2 = row1 + 8.5
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row2,
        page_h=page_h,
        fonts=fonts,
        cells=[
            (68.6, "INSCRICAO ESTADUAL", vm.emit_ie or "—"),
            (48.3, "INSCR. ESTADUAL SUBST. TRIB.", vm.emit_ie_st or "—"),
            (88.1, "CNPJ", format_document(vm.emit_cnpj)),
        ],
    )


def _row_cells(widths: tuple[float, ...], fields: tuple[tuple[str, str], ...]) -> list[tuple[float, str, str]]:
    return [(w, label, value) for w, (label, value) in zip(widths, fields, strict=True)]


def _draw_dest(c, vm, fonts, left, page_h) -> None:
    w = content_width_mm()
    d = vm.dest_address_parts
    draw_section_band(
        c,
        left_pt=left,
        top_mm=DEST_TOP,
        width_mm=w,
        page_h=page_h,
        title="DESTINATÁRIO / REMETENTE",
        fonts=fonts,
    )
    row1 = DEST_TOP + 4.2
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row1,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            DEST_ROW1_WIDTHS_MM,
            (
                ("RAZAO SOCIAL", vm.dest_name or "—"),
                ("CNPJ/CPF", format_document(vm.dest_doc)),
                ("DATA DA EMISSAO", format_date_br(vm.issue_date)),
            ),
        ),
    )
    row2 = row1 + 8.5
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row2,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            DEST_ROW2_WIDTHS_MM,
            (
                ("ENDERECO", d.street_line or "—"),
                ("BAIRRO/DISTRITO", d.bairro or "—"),
                ("CEP", format_cep(d.cep) or "—"),
                ("DATA ENTRADA/SAIDA", format_date_br(vm.exit_date or vm.issue_date)),
            ),
        ),
    )
    row3 = row2 + 8.5
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row3,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            DEST_ROW3_WIDTHS_MM,
            (
                ("MUNICIPIO", d.municipio or "—"),
                ("FONE/FAX", format_phone_br(vm.dest_phone) if vm.dest_phone else "—"),
                ("UF", d.uf or vm.dest_uf or "—"),
                ("INSCRICAO ESTADUAL", vm.dest_ie or "—"),
                ("HORA ENTRADA/SAIDA", format_time_br(vm.exit_date or vm.issue_date)),
            ),
        ),
    )


def _draw_delivery(c, vm, fonts, left, page_h, offs: Page1Offsets) -> None:
    w = content_width_mm()
    d = vm.delivery_address_parts
    top = offs.delivery_top or (DEST_TOP + DEST_HEIGHT)
    draw_section_band(
        c,
        left_pt=left,
        top_mm=top,
        width_mm=w,
        page_h=page_h,
        title="INFORMAÇÕES DO LOCAL DE ENTREGA",
        fonts=fonts,
    )
    row1 = top + 4.2
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row1,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            DELIVERY_ROW1_WIDTHS_MM,
            (
                ("RAZAO SOCIAL", vm.delivery_name or vm.dest_name or "—"),
                ("CNPJ/CPF", format_document(vm.delivery_doc or vm.dest_doc)),
                ("INSCRICAO ESTADUAL", vm.delivery_ie or "—"),
            ),
        ),
    )
    row2 = row1 + 8.5
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row2,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            DELIVERY_ROW2_WIDTHS_MM,
            (
                ("ENDERECO", d.street_line or vm.delivery_address[:60] or "—"),
                ("BAIRRO/DISTRITO", d.bairro or "—"),
                ("CEP", format_cep(d.cep) or "—"),
                ("MUNICIPIO", d.municipio or "—"),
                ("UF", d.uf or "—"),
            ),
        ),
    )


def _draw_billing(c, vm, fonts, left, page_h, offs: Page1Offsets) -> None:
    w = content_width_mm()
    draw_section_band(
        c,
        left_pt=left,
        top_mm=offs.billing_top,
        width_mm=w,
        page_h=page_h,
        title="FATURA / DUPLICATAS",
        fonts=fonts,
    )
    dup_lines = []
    for dup in vm.duplicates[:6]:
        dup_lines.append(
            f"{dup.number or '—'}  {format_date_br(dup.due_date) if dup.due_date else '—'}  "
            f"{format_money_br(dup.amount)}"
        )
    draw_cell(
        c,
        left_pt=left,
        top_mm=offs.billing_top + 4.2,
        width_mm=w,
        height_mm=8.5,
        page_h=page_h,
        label="FATURA",
        value=(
            f"N. {vm.invoice_number_fat or '—'}  "
            f"V. Orig. {format_money_br(vm.invoice_value_fat)}  "
            + "  ".join(dup_lines)
        ),
        fonts=fonts,
        value_pt=FONT_FIELD_VALUE,
    )


def _draw_tax_totals(c, vm, fonts, left, page_h, offs: Page1Offsets) -> None:
    w = content_width_mm()
    t = vm.totals
    draw_section_band(
        c,
        left_pt=left,
        top_mm=offs.tax_top,
        width_mm=w,
        page_h=page_h,
        title="CÁLCULO DO IMPOSTO",
        fonts=fonts,
    )
    row1 = offs.tax_top + 4.2
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row1,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            TAX_ROW1_WIDTHS_MM,
            (
                ("BASE CALC. ICMS", format_money_br(t.icms_base)),
                ("VALOR DO ICMS", format_money_br(t.icms_value)),
                ("BASE CALC. ICMS ST", format_money_br(t.icms_st_base)),
                ("VALOR DO ICMS ST", format_money_br(t.icms_st_value)),
                ("VALOR TOTAL PRODUTOS", format_money_br(t.products)),
            ),
        ),
        value_align_right_from=0,
    )
    approx = format_money_br(t.approx_taxes) if (t.approx_taxes or "").strip() not in ("", "0", "0.00") else "—"
    row2 = row1 + 8.5
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row2,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            TAX_ROW2_WIDTHS_MM,
            (
                ("VALOR DO FRETE", format_money_br(t.freight)),
                ("VALOR DO SEGURO", format_money_br(t.insurance)),
                ("DESCONTO", format_money_br(t.discount)),
                ("OUTRAS DESP.", format_money_br(t.other)),
                ("VALOR DO IPI", format_money_br(t.ipi_value)),
                ("VALOR APROX. TRIB.", approx),
                ("VALOR TOTAL DA NOTA", format_money_br(t.total_nf)),
            ),
        ),
        value_bold_last=True,
        value_align_right_from=0,
    )


def _draw_transport(c, vm, fonts, left, page_h, offs: Page1Offsets) -> None:
    w = content_width_mm()
    tr = vm.transport
    mod = {"0": "0-Remetente", "1": "1-Destinatario", "2": "2-Terceiros", "9": "9-Sem frete"}.get(
        tr.freight_mod, tr.freight_mod
    )
    draw_section_band(
        c,
        left_pt=left,
        top_mm=offs.transport_top,
        width_mm=w,
        page_h=page_h,
        title="TRANSPORTADOR / VOLUMES TRANSPORTADOS",
        fonts=fonts,
    )
    row1 = offs.transport_top + 4.2
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row1,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            TRANSPORT_ROW1_WIDTHS_MM,
            (
                ("RAZAO SOCIAL", tr.carrier_name or "—"),
                ("FRETE POR CONTA", mod),
                ("CODIGO ANTT", "—"),
                ("PLACA", tr.vehicle_plate or "—"),
                ("UF", tr.vehicle_uf or "—"),
                ("CNPJ/CPF", format_document(tr.carrier_doc) if tr.carrier_doc else "—"),
            ),
        ),
    )
    row2 = row1 + 8.5
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row2,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            TRANSPORT_ROW2_WIDTHS_MM,
            (
                ("ENDERECO", "—"),
                ("MUNICIPIO", tr.carrier_city or "—"),
                ("UF", tr.carrier_uf or "—"),
                ("INSCRICAO ESTADUAL", tr.carrier_ie or "—"),
            ),
        ),
    )
    row3 = row2 + 8.5
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=row3,
        page_h=page_h,
        fonts=fonts,
        cells=_row_cells(
            TRANSPORT_ROW3_WIDTHS_MM,
            (
                ("QUANTIDADE", tr.volumes_qty or "—"),
                ("ESPECIE", tr.volumes_species or "—"),
                ("MARCA", "—"),
                ("NUMERACAO", "—"),
                ("PESO BRUTO", format_weight_br(tr.gross_weight) if tr.gross_weight else "—"),
                ("PESO LIQUIDO", format_weight_br(tr.net_weight) if tr.net_weight else "—"),
            ),
        ),
        value_align_right_from=4,
    )


def _draw_issqn(c, vm, fonts, left, page_h, offs: Page1Offsets) -> None:
    w = content_width_mm()
    draw_section_band(
        c,
        left_pt=left,
        top_mm=offs.issqn_top,
        width_mm=w,
        page_h=page_h,
        title="CÁLCULO DO ISSQN",
        fonts=fonts,
    )
    draw_cells_row(
        c,
        left_pt=left,
        top_mm=offs.issqn_top + 4.2,
        page_h=page_h,
        height_mm=ISSQN_HEIGHT - 4.2,
        fonts=fonts,
        cells=[
            (50.8, "INSCRICAO MUNICIPAL", "—"),
            (50.8, "VALOR TOTAL SERVICOS", "—"),
            (50.8, "BASE CALCULO ISSQN", "—"),
            (53.3, "VALOR ISSQN", "—"),
        ],
    )


def _draw_item_column_grid(
    c,
    left_pt: float,
    *,
    top_mm: float,
    bottom_mm: float,
    page_h: float,
) -> None:
    """Linhas verticais — grid 13 colunas."""
    y_top_pt = y_top(page_h, top_mm)
    y_bottom_pt = y_top(page_h, bottom_mm)
    for x_mm in item_column_offsets_mm()[1:-1]:
        x_pt = left_pt + mm_to_pt(x_mm)
        c.line(x_pt, y_top_pt, x_pt, y_bottom_pt)


def _item_headers(vm: DanfeViewModel) -> tuple[str, ...]:
    return (
        "CODIGO",
        "DESCRICAO",
        "NCM/SH",
        _tax_col_label(vm),
        "CFOP",
        "UN",
        "QTD",
        "V.UNIT",
        "V.TOTAL",
        "BC ICMS",
        "V.ICMS",
        "ALQ ICMS",
        "V.APROX TRIB",
    )


_ITEM_VALUE_RIGHT_ALIGN_FROM = 6


def _draw_item_cell(c, *, left_pt: float, col_w_mm: float, y: float, text: str, col_idx: int) -> None:
    pad = mm_to_pt(0.6)
    clipped = danfe_upper(text)[: int(col_w_mm / 1.8)]
    col_w_pt = mm_to_pt(col_w_mm)
    if col_idx >= _ITEM_VALUE_RIGHT_ALIGN_FROM:
        c.drawRightString(left_pt + col_w_pt - pad, y, clipped)
    else:
        c.drawString(left_pt + pad, y, clipped)


def _draw_items(c, vm, plan, fonts, left, width, page_h, *, items_header_top_mm: float) -> None:
    from integrations.sefaz_nfe.danfe.layout import ITEM_COL_WIDTHS_MM

    draw_section_band(
        c,
        left_pt=left,
        top_mm=items_header_top_mm - 4.2,
        width_mm=content_width_mm(),
        page_h=page_h,
        title="DADOS DOS PRODUTOS / SERVICOS",
        fonts=fonts,
    )
    _rect_mm(c, left, items_header_top_mm, width, ITEMS_HEADER_HEIGHT, page_h)
    x_mm = 0.0
    headers = _item_headers(vm)
    for col_w, label in zip(ITEM_COL_WIDTHS_MM, headers, strict=True):
        draw_cell(
            c,
            left_pt=left + mm_to_pt(x_mm),
            top_mm=items_header_top_mm,
            width_mm=col_w,
            height_mm=ITEMS_HEADER_HEIGHT,
            page_h=page_h,
            label=label,
            value="",
            fonts=fonts,
            label_pt=FONT_TABLE_HEADER,
            value_pt=FONT_TABLE_BODY,
        )
        x_mm += col_w

    y_mm = items_header_top_mm + ITEMS_HEADER_HEIGHT
    row_h = 4.25
    c.setFont(fonts["body"], FONT_TABLE_BODY)
    for row_plan in plan.item_rows:
        item = vm.items[row_plan.item_index]
        values = [
            item.code[:12],
            row_plan.lines[0][:36],
            item.ncm[:8],
            _tax_code_display(item, vm)[:4],
            item.cfop[:4],
            item.unit[:3],
            format_qty(item.quantity),
            format_unit_price(item.unit_price),
            format_money_br(item.total),
            format_money_br(item.icms_base),
            format_money_br(item.icms_value),
            format_rate_br(item.icms_rate) if item.icms_rate else "—",
            format_money_br(item.approx_taxes) if item.approx_taxes else "—",
        ]
        y = y_top(page_h, y_mm + 3.0)
        x_mm = 0.0
        for col_idx, (col_w, val) in enumerate(zip(ITEM_COL_WIDTHS_MM, values, strict=True)):
            _draw_item_cell(c, left_pt=left + mm_to_pt(x_mm), col_w_mm=col_w, y=y, text=val, col_idx=col_idx)
            x_mm += col_w
        y_mm += row_h
        _hline_mm(c, left, y_mm, width, page_h)
        for extra in row_plan.lines[1:]:
            y = y_top(page_h, y_mm + 3.0)
            c.drawString(left + mm_to_pt(ITEM_COL_WIDTHS_MM[0] + 0.6), y, danfe_upper(extra)[:90])
            y_mm += row_h
            _hline_mm(c, left, y_mm, width, page_h)

    if plan.item_rows:
        _draw_item_column_grid(
            c,
            left,
            top_mm=items_header_top_mm,
            bottom_mm=y_mm,
            page_h=page_h,
        )


def _draw_additional_info(c, vm, plan, fonts, left, width, page_h) -> None:
    content_h = mm_to_pt(FOOTER_CONTENT_HEIGHT)
    footer_top = footer_info_top_mm(has_delivery=plan.show_delivery)
    top_y = y_top(page_h, footer_top)
    split = left + width * FOOTER_INFO_SPLIT_RATIO
    c.setLineWidth(STROKE_PT)
    c.rect(left, top_y - content_h, width, content_h)
    c.line(split, top_y, split, top_y - content_h)

    left_w = split - left - mm_to_pt(3)
    right_w = left + width - split - mm_to_pt(3)
    y = top_y - mm_to_pt(2.0)
    c.setFont(fonts["bold"], FONT_BLOCK_TITLE)
    cpl_title = "INFORMAÇÕES COMPLEMENTARES"
    if plan.inf_cpl_continuation:
        cpl_title += " (CONT.)"
    c.drawString(left + mm_to_pt(2), y, _fit_text(c, cpl_title, fonts["bold"], FONT_BLOCK_TITLE, left_w))
    if not plan.inf_cpl_continuation:
        c.drawString(split + mm_to_pt(2), y, "RESERVADO AO FISCO")
    y -= mm_to_pt(3.5)
    c.setFont(fonts["body"], FONT_BODY)
    from integrations.sefaz_nfe.danfe.pagination import inf_cpl_display_text

    cpl_lines = plan.footer_inf_cpl_lines or _wrap_lines(inf_cpl_display_text(vm), 78)
    for line in cpl_lines[:8]:
        c.drawString(left + mm_to_pt(2), y, _fit_text(c, line, fonts["body"], FONT_BODY, left_w))
        y -= mm_to_pt(2.8)
    if not plan.inf_cpl_continuation:
        y2 = top_y - mm_to_pt(5.5)
        fisco_lines = plan.footer_fisco_lines or _wrap_lines(vm.inf_ad_fisco or "SEM INFORMACOES.", 28)
        for line in fisco_lines[:5]:
            c.drawString(split + mm_to_pt(2), y2, _fit_text(c, line, fonts["body"], FONT_BODY, right_w))
            y2 -= mm_to_pt(2.8)

    tech_top = footer_top + FOOTER_CONTENT_HEIGHT
    tech_y = y_top(page_h, tech_top + 2.5)
    c.setFont(fonts["body"], 6)
    c.drawString(
        left + mm_to_pt(2),
        tech_y,
        _fit_text(c, f"EXEQ Hub DANFE | {LAYOUT_VERSION}", fonts["body"], 6, width * 0.55),
    )
    gen = f"Gerado em {format_datetime_br(vm.issue_date)}"
    c.drawRightString(
        left + width - mm_to_pt(2),
        tech_y,
        _fit_text(c, gen, fonts["body"], 6, width * 0.42),
    )


def _wrap_lines(text: str, max_chars: int) -> list[str]:
    from integrations.sefaz_nfe.danfe.formatters import wrap_text

    return wrap_text(text, max_chars=max_chars) or [""]


def _watermark_cancelled(c, page_w, page_h, fonts) -> None:
    c.saveState()
    c.setFillColor(red)
    if hasattr(c, "setFillAlpha"):
        c.setFillAlpha(0.15)
    c.setFont(fonts["title"], 48)
    c.translate(page_w / 2, page_h / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "CANCELADA")
    c.restoreState()


def _watermark_homolog(c, page_w, page_h, fonts) -> None:
    c.saveState()
    c.setFillColor(red)
    if hasattr(c, "setFillAlpha"):
        c.setFillAlpha(0.12)
    c.setFont(fonts["title"], 22)
    c.translate(page_w / 2, page_h / 2)
    c.rotate(25)
    c.drawCentredString(0, 0, "SEM VALOR FISCAL")
    c.restoreState()
