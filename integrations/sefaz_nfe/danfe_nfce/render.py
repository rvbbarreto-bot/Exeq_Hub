"""DANFE NFC-e cupom (80mm) — layout EXEQ v0.1."""

from __future__ import annotations

import io

from reportlab.graphics.barcode import qr
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from integrations.sefaz_nfe.danfe.fields import extract_danfe_fields
from integrations.sefaz_nfe.danfe.render import _fonts, _format_key

LAYOUT_VERSION = "exeq-danfce-0.1"
_PAGE_W = 8 * cm


def _qr_url_from_xml(xml_bytes: bytes) -> str:
    from integrations.nfse.xml_safe import safe_fromstring

    root = safe_fromstring(xml_bytes)
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "qrCode" and el.text:
            return (el.text or "").strip()
    return ""


def render_danfce_pdf(xml_bytes: bytes, *, cancelled: bool = False) -> bytes:
    fields = extract_danfe_fields(xml_bytes)
    fonts = _fonts()
    qr_url = _qr_url_from_xml(xml_bytes)

    line_h = 0.38 * cm
    base_h = 16 * cm
    extra = min(len(fields.items), 12) * line_h
    page_h = base_h + extra

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_PAGE_W, page_h))
    c.setTitle(f"DANFC-e {fields.series}/{fields.number}")
    c.setCreator("EXEQ Hub")

    y = page_h - 0.4 * cm
    margin = 0.25 * cm
    width = _PAGE_W - 2 * margin

    def line(text: str, *, bold: bool = False, size: int = 8) -> None:
        nonlocal y
        c.setFont(fonts["title"] if bold else fonts["body"], size)
        c.drawCentredString(_PAGE_W / 2, y, (text or "")[:48])
        y -= line_h

    def left(text: str, *, size: int = 7) -> None:
        nonlocal y
        c.setFont(fonts["body"], size)
        c.drawString(margin, y, (text or "")[:52])
        y -= line_h * 0.9

    line(fields.emit_name, bold=True, size=9)
    line(f"CNPJ {fields.emit_cnpj}  IE {fields.emit_ie or '—'}", size=7)
    line(fields.emit_address[:48], size=7)
    y -= 0.1 * cm
    line("DOCUMENTO AUXILIAR DA NFC-e", bold=True, size=8)
    if cancelled:
        line("*** CANCELADA ***", bold=True, size=9)
    amb = "HOMOLOGAÇÃO" if fields.tp_amb == "2" else "PRODUÇÃO"
    line(f"Modelo 65 · {amb}", size=7)
    y -= 0.1 * cm

    left(f"Nº {fields.series}/{fields.number}  Emissão: {(fields.issue_date or '')[:10]}")
    left(f"Chave: {_format_key(fields.access_key)}")
    if fields.protocol:
        left(f"Protocolo: {fields.protocol}")
    y -= 0.15 * cm

    left("ITENS", size=7)
    for it in fields.items[:12]:
        desc = it.get("desc") or ""
        qty = it.get("qty") or "1"
        unit = it.get("unit") or "UN"
        total = it.get("vprod") or "0.00"
        left(f"{desc[:28]}")
        left(f"  {qty} {unit} x R$ {it.get('vun','0')} = R$ {total}", size=6)
    y -= 0.1 * cm

    line(f"TOTAL R$ {fields.total_nf}", bold=True, size=10)
    if fields.dest_doc:
        left(f"Consumidor CPF/CNPJ: {fields.dest_doc}")
    y -= 0.2 * cm

    if qr_url:
        try:
            code = qr.QrCodeWidget(qr_url)
            bounds = code.getBounds()
            bw = bounds[2] - bounds[0]
            bh = bounds[3] - bounds[1]
            size = min(width * 0.55, 3.2 * cm)
            x = (_PAGE_W - size) / 2
            c.saveState()
            c.translate(x, y - size)
            c.scale(size / bw, size / bh)
            code.drawOn(c, 0, 0)
            c.restoreState()
            y -= size + 0.2 * cm
        except Exception:  # noqa: BLE001
            left("QR indisponível")

    c.setFont(fonts["body"], 6)
    c.drawCentredString(
        _PAGE_W / 2,
        0.35 * cm,
        f"Consulte pela chave ou QR · Layout {LAYOUT_VERSION}",
    )
    c.showPage()
    c.save()
    return buf.getvalue()
