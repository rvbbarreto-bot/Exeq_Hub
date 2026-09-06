"""DANFE NFC-e cupom 80 mm — layout exeq-danfce-1.0 (Manual v6.0 + modelo PO)."""

from __future__ import annotations

import io
from typing import Any

from reportlab.graphics.barcode import qr
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from integrations.sefaz_nfe.danfe.render import _fonts, _format_key
from integrations.sefaz_nfe.danfe_nfce.fields import DanfceFields, extract_danfce_fields
from integrations.sefaz_nfe.danfe_nfce.format import (
    format_br_money,
    format_br_qty,
    format_dh_emi,
    format_nfce_number,
    format_series,
    mask_cnpj,
    mask_cpf,
    pct_from_values,
    sum_item_quantities,
    tpag_label,
    wrap_center,
)

LAYOUT_VERSION = "exeq-danfce-1.0"
_PAGE_W = 8 * cm
_MARGIN = 0.25 * cm
_LINE = 0.36 * cm
_QR_MIN = 2.5 * cm
_FOOTER_H = 0.45 * cm


def render_danfce_pdf(
    xml_bytes: bytes,
    *,
    cancelled: bool = False,
    protocol_override: str = "",
    auth_at_override: str = "",
) -> bytes:
    fields = extract_danfce_fields(
        xml_bytes,
        cancelled=cancelled,
        protocol_override=protocol_override,
        auth_at_override=auth_at_override,
    )
    if not fields.qr_code:
        fields.qr_code = _qr_from_xml(xml_bytes)
    return _render_fields(fields)


def render_danfce_for_invoice(invoice: Any, xml_bytes: bytes, *, cancelled: bool = False) -> bytes:
    """Render on-demand com metadados da invoice (protocolo SEFAZ)."""
    from apps.nfce.models import NfceInvoice

    is_cancelled = cancelled or invoice.status == NfceInvoice.Status.CANCELLED
    auth_at = _auth_at_from_invoice(invoice)
    return render_danfce_pdf(
        xml_bytes,
        cancelled=is_cancelled,
        protocol_override=getattr(invoice, "protocol", "") or "",
        auth_at_override=auth_at,
    )


def _auth_at_from_invoice(invoice: Any) -> str:
    snap = invoice.fiscal_snapshot if isinstance(getattr(invoice, "fiscal_snapshot", None), dict) else {}
    sefaz = snap.get("sefaz") if isinstance(snap.get("sefaz"), dict) else {}
    return str(sefaz.get("dh_recbto") or "").strip()


def _qr_from_xml(xml_bytes: bytes) -> str:
    from integrations.nfse.xml_safe import safe_fromstring

    root = safe_fromstring(xml_bytes)
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "qrCode" and el.text:
            return (el.text or "").strip()
    return ""


def _estimate_page_height(fields: DanfceFields) -> float:
    """Altura dinâmica — evita sobreposição no rodapé/QR."""
    lines = 0.0
    lines += 12  # cabeçalho + título
    if fields.cancelled:
        lines += 1
    if fields.tp_amb == "2":
        lines += 2
    lines += 2 + min(len(fields.items), 24)  # tabela itens
    lines += 2  # totais base
    if Decimal_gt(fields.discount, "0"):
        lines += 1
    if Decimal_gt(fields.freight, "0"):
        lines += 1
    if fields.payments:
        lines += 1 + len(fields.payments)
        if fields.change and Decimal_gt(fields.change, "0"):
            lines += 1
    if fields.v_cbs or fields.v_ibs:
        lines += 4
    elif fields.v_tot_trib and Decimal_gt(fields.v_tot_trib, "0"):
        lines += 3
    lines += 1  # consumidor
    lines += 2  # nfc-e nº + emissão
    if fields.protocol:
        lines += 1
        if fields.auth_datetime:
            lines += 1
    if fields.url_chave:
        lines += 1 + len(wrap_center(fields.url_chave, width=44))
    if fields.access_key:
        lines += 1
    if fields.qr_code:
        qr_h = _QR_MIN / _LINE
        lines += qr_h + 1
    lines += 2  # separadores + footer
    return max(16 * cm, lines * _LINE + _FOOTER_H + 0.8 * cm)


def _draw_qr_code(c: canvas.Canvas, url: str, *, x: float, y: float, size: float) -> bool:
    """Gera QR via qrcode+PIL (URLs NFC-e longas); fallback ReportLab."""
    try:
        import qrcode
        from reportlab.lib.utils import ImageReader

        qr_img = qrcode.make(url, box_size=4, border=2)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        c.drawImage(ImageReader(buf), x, y, width=size, height=size, mask="auto")
        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        code = qr.QrCodeWidget(url)
        bounds = code.getBounds()
        bw = bounds[2] - bounds[0]
        bh = bounds[3] - bounds[1]
        c.saveState()
        c.translate(x, y)
        c.scale(size / bw, size / bh)
        code.drawOn(c, 0, 0)
        c.restoreState()
        return True
    except Exception:  # noqa: BLE001
        return False


def _render_fields(fields: DanfceFields) -> bytes:
    fonts = _fonts()
    line_h = _LINE
    page_h = _estimate_page_height(fields)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_PAGE_W, page_h))
    c.setTitle(f"DANFC-e {fields.series}/{fields.number}")
    c.setSubject(f"danfce_layout_version={LAYOUT_VERSION}")
    c.setCreator("EXEQ Hub")

    y = page_h - 0.35 * cm
    width = _PAGE_W - 2 * _MARGIN

    def rule(char: str = "=") -> None:
        nonlocal y
        c.setFont(fonts["body"], 6)
        c.drawCentredString(_PAGE_W / 2, y, char * 48)
        y -= line_h * 0.9

    def center(text: str, *, bold: bool = False, size: int = 7) -> None:
        nonlocal y
        c.setFont(fonts["title"] if bold else fonts["body"], size)
        c.drawCentredString(_PAGE_W / 2, y, (text or "")[:54])
        y -= line_h

    def center_wrap(text: str, *, bold: bool = False, size: int = 6) -> None:
        for part in wrap_center(text, width=48):
            center(part, bold=bold, size=size)

    def left(text: str, *, size: int = 6.5) -> None:
        nonlocal y
        c.setFont(fonts["body"], size)
        c.drawString(_MARGIN, y, (text or "")[:58])
        y -= line_h * 0.92

    def left_right(left_text: str, right_text: str, *, size: int = 6.5) -> None:
        nonlocal y
        c.setFont(fonts["body"], size)
        c.drawString(_MARGIN, y, left_text[:38])
        c.drawRightString(_PAGE_W - _MARGIN, y, right_text[:18])
        y -= line_h * 0.92

    def ensure_space(min_y: float) -> None:
        nonlocal y
        if y < min_y:
            y = min_y

    # Divisão I — Cabeçalho
    rule("=")
    center(fields.emit_name, bold=True, size=8)
    cnpj = mask_cnpj(fields.emit_cnpj) if len("".join(ch for ch in fields.emit_cnpj if ch.isdigit())) >= 14 else fields.emit_cnpj
    ie = fields.emit_ie or "ISENTO"
    center(f"CNPJ: {cnpj}  IE: {ie}", size=6)
    if fields.emit_address:
        center_wrap(fields.emit_address, size=6)
    rule("=")

    center("DANFE NFC-e - Documento Auxiliar", bold=True, size=7)
    center("da Nota Fiscal de Consumidor Eletrônica", size=6)
    rule("=")

    if fields.cancelled:
        center("*** CANCELADA ***", bold=True, size=8)
        rule("=")

    if fields.tp_amb == "2":
        center("EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO", bold=True, size=6)
        center("SEM VALOR FISCAL", bold=True, size=6)
        y -= line_h * 0.15

    # Divisão II — Itens
    left("#  CÓDIGO   DESCRIÇÃO          QTD UN  V.UNIT  V.TOTAL", size=5.5)
    rule("-")
    for it in fields.items[:24]:
        idx = str(it.get("n_item") or "1").zfill(3)
        code = (it.get("code") or "")[:8]
        desc = (it.get("desc") or "")[:14]
        qty = format_br_qty(it.get("qty") or "1")
        unit = (it.get("unit") or "UN")[:3]
        vun = format_br_money(it.get("vun") or "0")
        vtot = format_br_money(it.get("vprod") or "0")
        row = f"{idx} {code:<8} {desc:<14} {qty:>4} {unit:>2} {vun:>7} {vtot:>7}"
        left(row, size=5.5)
    rule("-")

    # Divisão III — Totais (soma unidades compradas)
    left_right("QTD. TOTAL DE ITENS:", fields.total_units or "0")
    left_right("VALOR TOTAL R$:", format_br_money(fields.total_nf))
    if Decimal_gt(fields.discount, "0"):
        left_right("DESCONTO R$:", format_br_money(fields.discount))
    if Decimal_gt(fields.freight, "0"):
        left_right("FRETE R$:", format_br_money(fields.freight))

    if fields.payments:
        left("FORMA DE PAGAMENTO              VALOR (R$)", size=6)
        for pay in fields.payments:
            label = tpag_label(pay.get("tPag") or "99")
            left_right(label[:28], format_br_money(pay.get("vPag") or "0"))
        if fields.change and Decimal_gt(fields.change, "0"):
            left_right("TROCO R$:", format_br_money(fields.change))
    rule("=")

    if fields.v_cbs or fields.v_ibs:
        center("INFORMACAO DOS TRIBUTOS TOTAIS INCIDENTES", bold=True, size=6)
        center("(Lei Federal 12.741/2012 / LC 214/2025)", size=5.5)
        base = fields.v_bc_rtc or fields.products
        if fields.v_cbs:
            pct = pct_from_values(fields.v_cbs, base)
            left_right("CBS (Federal):", f"R$ {format_br_money(fields.v_cbs)} ({pct}%)")
        if fields.v_ibs:
            pct = pct_from_values(fields.v_ibs, base)
            left_right("IBS (Est./Mun.):", f"R$ {format_br_money(fields.v_ibs)} ({pct}%)")
        rule("=")
    elif fields.v_tot_trib and Decimal_gt(fields.v_tot_trib, "0"):
        center("INFORMACAO DOS TRIBUTOS TOTAIS INCIDENTES", bold=True, size=6)
        center("(Lei Federal 12.741/2012)", size=5.5)
        left_right("Tributos aprox.:", f"R$ {format_br_money(fields.v_tot_trib)}")
        rule("=")

    # Divisão VI — Consumidor
    if fields.dest_kind == "cpf":
        center(f"CONSUMIDOR: CPF {mask_cpf(fields.dest_doc)}", size=6)
    elif fields.dest_kind == "cnpj":
        center(f"CONSUMIDOR: CNPJ {mask_cnpj(fields.dest_doc)}", size=6)
    elif fields.dest_kind == "foreign":
        center_wrap(f"CONSUMIDOR Id. Estrangeiro: {fields.dest_doc}", size=6)
    else:
        center("CONSUMIDOR NÃO IDENTIFICADO", size=6)
    y -= line_h * 0.1

    # Divisão VII — Identificação + protocolo (linhas separadas)
    emi = format_dh_emi(fields.issue_date)
    center(
        f"NFC-e nº {format_nfce_number(fields.number)}  Série {format_series(fields.series)}",
        size=6,
    )
    center(f"Emissão: {emi}", size=6)
    if fields.protocol:
        center_wrap(f"Protocolo de Autorização: {fields.protocol}", size=6)
        if fields.auth_datetime:
            auth = format_dh_emi(fields.auth_datetime)
            center(f"Autorização: {auth}", size=6)
    rule("=")

    # Divisão IV — Chave
    if fields.url_chave:
        center("Consulte pela Chave de Acesso em", size=5.5)
        center_wrap(fields.url_chave, size=5)
    if fields.access_key:
        center(_format_key(fields.access_key), size=5.5)
    y -= line_h * 0.15

    # Divisão V — QR Code (antes do footer, com espaço garantido)
    qr_size = max(_QR_MIN, min(width * 0.72, 3.0 * cm))
    min_y_for_qr = _FOOTER_H + qr_size + 0.35 * cm
    if fields.qr_code:
        ensure_space(min_y_for_qr + line_h * 2)
        qr_x = (_PAGE_W - qr_size) / 2
        qr_y = y - qr_size
        if qr_y < _FOOTER_H + 0.2 * cm:
            qr_y = _FOOTER_H + 0.2 * cm
        if _draw_qr_code(c, fields.qr_code, x=qr_x, y=qr_y, size=qr_size):
            y = qr_y - line_h * 0.5
            center("Consulta via leitor de QR Code", size=6)
        else:
            center("QR Code indisponível", size=6)

    rule("=")
    c.setFont(fonts["body"], 5)
    c.drawCentredString(_PAGE_W / 2, 0.28 * cm, f"Layout {LAYOUT_VERSION} · EXEQ Hub")
    c.showPage()
    c.save()
    return buf.getvalue()


def Decimal_gt(raw: str, threshold: str) -> bool:
    from decimal import Decimal

    try:
        return Decimal(str(raw).replace(",", ".")) > Decimal(str(threshold).replace(",", "."))
    except Exception:  # noqa: BLE001
        return False
