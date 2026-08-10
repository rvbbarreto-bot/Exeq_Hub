"""DANFE PDF (layout EXEQ I2) — A4 a partir do XML NFe. Sem reverter authorized."""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib.colors import black, lightgrey, red
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from integrations.sefaz_nfe.danfe.fields import DanfeFields, extract_danfe_fields

LAYOUT_VERSION = "exeq-danfe-0.1"
_MARGIN = 0.8 * cm


def render_danfe_pdf(xml_bytes: bytes, *, cancelled: bool = False) -> bytes:
    fields = extract_danfe_fields(xml_bytes, cancelled=cancelled)
    fonts = _fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setTitle(f"DANFE {fields.series}/{fields.number}")
    c.setSubject(f"danfe_layout_version={LAYOUT_VERSION}")
    c.setCreator("EXEQ Hub")

    c.setStrokeColor(black)
    c.setLineWidth(1)
    c.rect(_MARGIN, _MARGIN, w - 2 * _MARGIN, h - 2 * _MARGIN)

    if fields.cancelled or cancelled:
        c.saveState()
        c.setFillColor(red)
        if hasattr(c, "setFillAlpha"):
            c.setFillAlpha(0.18)
        c.setFont(fonts["title"], 48)
        c.translate(w / 2, h / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "CANCELADA")
        c.restoreState()

    y = h - _MARGIN - 0.6 * cm
    c.setFont(fonts["title"], 11)
    c.drawString(_MARGIN + 0.3 * cm, y, "DANFE — Documento Auxiliar da Nota Fiscal Eletrônica")
    y -= 0.45 * cm
    c.setFont(fonts["body"], 8)
    amb = "HOMOLOGAÇÃO" if fields.tp_amb == "2" else "PRODUÇÃO"
    c.drawString(_MARGIN + 0.3 * cm, y, f"Modelo 55 · Ambiente: {amb} · Layout {LAYOUT_VERSION}")
    y -= 0.55 * cm

    y = _box(
        c,
        y,
        w,
        fonts,
        "IDENTIFICAÇÃO",
        [
            f"Série/Nº: {fields.series}/{fields.number}",
            f"Natureza: {fields.nature}",
            f"Emissão: {fields.issue_date}",
            f"Chave: {_format_key(fields.access_key)}",
            f"Protocolo: {fields.protocol or '—'}",
        ],
    )
    y = _box(
        c,
        y,
        w,
        fonts,
        "EMITENTE",
        [
            fields.emit_name,
            f"CNPJ {fields.emit_cnpj}  IE {fields.emit_ie or '—'}",
            fields.emit_address,
        ],
    )
    y = _box(
        c,
        y,
        w,
        fonts,
        "DESTINATÁRIO",
        [
            fields.dest_name,
            f"Doc {fields.dest_doc}",
            fields.dest_address,
        ],
    )

    y = _section_title(c, y, w, fonts, "ITENS")
    c.setFont(fonts["body"], 7)
    headers = f"{'Cód':8} {'Descrição':32} {'NCM':8} {'CFOP':4} {'Qtd':8} {'V.Unit':10} {'Total':10}"
    c.drawString(_MARGIN + 0.3 * cm, y, headers)
    y -= 0.35 * cm
    for it in fields.items[:25]:
        if y < _MARGIN + 3 * cm:
            break
        line = (
            f"{it.get('code','')[:8]:8} "
            f"{it.get('desc','')[:32]:32} "
            f"{it.get('ncm','')[:8]:8} "
            f"{it.get('cfop','')[:4]:4} "
            f"{it.get('qty','')[:8]:8} "
            f"{it.get('vun','')[:10]:10} "
            f"{it.get('vprod','')[:10]:10}"
        )
        c.drawString(_MARGIN + 0.3 * cm, y, line)
        y -= 0.32 * cm

    y -= 0.2 * cm
    y = _box(
        c,
        y,
        w,
        fonts,
        "TOTAIS",
        [
            f"Produtos: R$ {fields.products}",
            f"Valor total da NF-e: R$ {fields.total_nf}",
        ],
    )

    c.setFont(fonts["body"], 7)
    c.drawString(
        _MARGIN + 0.3 * cm,
        _MARGIN + 0.35 * cm,
        "Documento auxiliar gerado pelo EXEQ Hub. Consulte a chave de acesso na SEFAZ.",
    )
    c.showPage()
    c.save()
    return buf.getvalue()


def _format_key(key: str) -> str:
    k = "".join(ch for ch in key if ch.isdigit())
    if len(k) != 44:
        return key or "—"
    return " ".join(k[i : i + 4] for i in range(0, 44, 4))


def _section_title(c, y, w, fonts, title: str) -> float:
    c.setFillColor(lightgrey)
    c.rect(_MARGIN + 0.15 * cm, y - 0.15 * cm, w - 2 * _MARGIN - 0.3 * cm, 0.4 * cm, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont(fonts["title"], 8)
    c.drawString(_MARGIN + 0.3 * cm, y, title)
    return y - 0.5 * cm


def _box(c, y, w, fonts, title: str, lines: list[str]) -> float:
    y = _section_title(c, y, w, fonts, title)
    c.setFont(fonts["body"], 8)
    for line in lines:
        if not line:
            continue
        c.drawString(_MARGIN + 0.3 * cm, y, line[:110])
        y -= 0.35 * cm
    return y - 0.25 * cm


def _fonts() -> dict[str, str]:
    title = "Helvetica-Bold"
    body = "Helvetica"
    try:
        regular = Path(r"C:\Windows\Fonts\arial.ttf")
        bold = Path(r"C:\Windows\Fonts\arialbd.ttf")
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont("DanfeArial", str(regular)))
            pdfmetrics.registerFont(TTFont("DanfeArial-Bold", str(bold)))
            title = "DanfeArial-Bold"
            body = "DanfeArial"
    except Exception:  # noqa: BLE001
        pass
    return {"title": title, "body": body}
