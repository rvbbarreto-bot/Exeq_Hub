"""Renderização PDF do DANFSe — NT SE/CGNFS-e 008/2026 v1.02 (Anexo I / M1 polish)."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import qrcode
from reportlab.lib.colors import Color, black, red
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from integrations.nfse.danfse.fields import DanfseFields, extract_danfse_fields
from integrations.nfse.danfse.formatters import (
    format_competencia,
    format_datetime_br,
    format_document,
    format_endereco_display,
    format_money_br,
    format_percent_br,
)
from integrations.nfse.xml_safe import safe_fromstring

LAYOUT_VERSION = "nt008-v1.02"
_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO_PATH = _ASSETS / "logo_nfse_horizontal.png"

# NT 008 §2.2.3 — cinza claro 5%; §2.5.1 CANCELADA K35.
_GRAY_HEADER = Color(0.95, 0.95, 0.95)
_QR_MIN_CM = 1.52
_MARGIN = 0.30 * cm


def render_danfse_pdf(
    xml_bytes: bytes,
    *,
    cancelled: bool = False,
) -> bytes:
    """Gera PDF A4 retrato, uma página, campos só do XML (RF-41a…d, RF-43, RF-47)."""
    fields = extract_danfse_fields(xml_bytes, cancelled=cancelled)
    fonts = _fonts()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setTitle(f"DANFSe v2.0 — {fields.numero}")
    c.setSubject(f"danfse_layout_version={LAYOUT_VERSION}")
    c.setCreator("EXEQ Hub")

    # Borda da página 1 pt (NT §2.2.3)
    c.setStrokeColor(black)
    c.setLineWidth(1)
    c.rect(_MARGIN, _MARGIN, width - 2 * _MARGIN, height - 2 * _MARGIN)

    # Watermark atrás do conteúdo (NT §2.5.1) — não cobrir títulos dos blocos.
    if fields.cancelled:
        _draw_cancelled_watermark(c, width, height, fonts)

    y = _draw_header(c, width, height, fields, fonts)
    y = _draw_identificacao(c, width, y, fields, fonts)
    y = _draw_prestador(c, width, y, fields, fonts)
    y = _draw_tomador(c, width, y, fields, fonts)
    y = _draw_servico(c, width, y, fields, fonts)
    y = _draw_valores(c, width, y, fields, fonts)
    _draw_complementares(c, width, y, fields, fonts)

    c.showPage()
    c.save()
    return buffer.getvalue()


@lru_cache(maxsize=1)
def _fonts() -> dict[str, str]:
    """Arial (títulos) + Microsoft Sans Serif (conteúdo); fallback Helvetica."""
    title = "Helvetica-Bold"
    body = "Helvetica"
    candidates = [
        (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf"),
         Path(r"C:\Windows\Fonts\micross.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
         Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
         Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
    ]
    for regular, bold, ms in candidates:
        try:
            if regular.is_file() and bold.is_file():
                pdfmetrics.registerFont(TTFont("DanfseArial", str(regular)))
                pdfmetrics.registerFont(TTFont("DanfseArial-Bold", str(bold)))
                title = "DanfseArial-Bold"
                body = "DanfseArial"
                if ms.is_file():
                    pdfmetrics.registerFont(TTFont("DanfseMSS", str(ms)))
                    body = "DanfseMSS"
                break
        except Exception:  # noqa: BLE001
            continue
    return {"title": title, "body": body}


def _draw_header(
    c: canvas.Canvas,
    width: float,
    height: float,
    fields: DanfseFields,
    fonts: dict[str, str],
) -> float:
    left = _MARGIN + 0.15 * cm
    top = height - _MARGIN

    # Logo oficial NFS-e (NT §2.4.3) — ~4,00 × 0,85 cm
    if _LOGO_PATH.is_file():
        logo_w, logo_h = 4.0 * cm, 0.85 * cm
        c.drawImage(
            str(_LOGO_PATH),
            left + 0.15 * cm,
            top - 0.45 * cm - logo_h,
            width=logo_w,
            height=logo_h,
            mask="auto",
            preserveAspectRatio=True,
            anchor="c",
        )

    # Centro: DANFSe v2.0 + subtítulo (Arial Bold 9)
    c.setFillColor(black)
    c.setFont(fonts["title"], 9)
    c.drawCentredString(width / 2, top - 1.0 * cm, "DANFSe v2.0")
    c.drawCentredString(width / 2, top - 1.4 * cm, "Documento Auxiliar da NFS-e")

    if fields.is_homologacao:
        c.setFillColor(red)
        c.setFont(fonts["title"], 9)
        c.drawCentredString(
            width / 2,
            top - 1.85 * cm,
            "NFS-e SEM VALIDADE JURÍDICA",
        )
        c.setFillColor(black)

    # Direita: município 8pt; ambiente 6pt
    right = width - _MARGIN - 0.2 * cm
    c.setFont(fonts["body"], 8)
    c.drawRightString(right - 1.7 * cm, top - 0.9 * cm, fields.municipio_emitente)
    c.setFont(fonts["body"], 6)
    c.drawRightString(right - 1.7 * cm, top - 1.25 * cm, "Sistema Nacional NFS-e")
    c.drawRightString(right - 1.7 * cm, top - 1.5 * cm, fields.ambiente)
    c.setFont(fonts["body"], 6)
    c.drawRightString(right - 1.7 * cm, top - 1.75 * cm, LAYOUT_VERSION)

    # QR Code coordenadas aproximadas NT (X≈17,48 cm; Y≈1,67 cm do topo; mín 1,52 cm)
    qr_side = _QR_MIN_CM * cm
    qr_x = 17.48 * cm
    qr_y = height - 1.67 * cm - qr_side
    c.drawImage(
        _qr_image(fields.qr_payload),
        qr_x,
        qr_y,
        width=qr_side,
        height=qr_side,
        mask="auto",
    )
    c.setFont(fonts["body"], 6)
    qr_caption = (
        "A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR "
        "ou pela consulta da chave de acesso no portal nacional da NFS-e"
    )
    _draw_wrapped(
        c,
        qr_caption,
        x=15.80 * cm,
        y=qr_y - 0.25 * cm,
        max_width=4.7 * cm,
        font=fonts["body"],
        size=6,
        leading=8,
        align="center",
        center_x=qr_x + qr_side / 2,
    )

    header_bottom = min(top - 2.5 * cm, qr_y - 1.1 * cm)
    return header_bottom - 0.15 * cm


def _draw_identificacao(c, width, y, fields, fonts) -> float:
    y = _block_title(c, width, y, "IDENTIFICAÇÃO DA NFS-e", fonts)
    y = _kv(c, width, y, "Chave de Acesso", _format_chave(fields.chave_acesso), fonts)
    y = _kv_row(
        c,
        width,
        y,
        fonts,
        ("Nº NFS-e", fields.numero),
        ("Competência", format_competencia(fields.competencia)),
        ("Situação", fields.situacao),
    )
    y = _kv_row(
        c,
        width,
        y,
        fonts,
        ("Data/Hora emissão", format_datetime_br(fields.data_emissao)),
        ("Nº DPS", fields.numero_dps),
        ("Série DPS", fields.serie_dps),
    )
    y = _kv_row(
        c,
        width,
        y,
        fonts,
        ("Data/Hora DPS", format_datetime_br(fields.data_emissao_dps)),
        ("Emitente", fields.emitente_nfse),
        ("Finalidade", fields.finalidade),
    )
    return y - 0.12 * cm


def _draw_prestador(c, width, y, fields, fonts) -> float:
    y = _block_title(c, width, y, "PRESTADOR / FORNECEDOR", fonts)
    y = _kv(c, width, y, "Nome", fields.prestador_nome, fonts, stacked=True)
    y = _kv_row(
        c,
        width,
        y,
        fonts,
        ("CNPJ/CPF/NIF", format_document(fields.prestador_doc)),
        ("IM", fields.prestador_im),
        ("Município", fields.prestador_municipio),
    )
    if fields.prestador_endereco not in {"", "—"}:
        y = _kv(
            c,
            width,
            y,
            "Endereço",
            format_endereco_display(fields.prestador_endereco),
            fonts,
            value_maxlen=110,
            stacked=True,
        )
    return y - 0.12 * cm


def _draw_tomador(c, width, y, fields, fonts) -> float:
    y = _block_title(c, width, y, "TOMADOR / ADQUIRENTE", fonts)
    if fields.tomador_nome in {"", "—"} and fields.tomador_doc in {"", "—"}:
        y = _kv(
            c,
            width,
            y,
            "",
            "TOMADOR/ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e",
            fonts,
        )
        return y - 0.12 * cm
    y = _kv(c, width, y, "Nome", fields.tomador_nome, fonts, stacked=True)
    y = _kv_row(
        c,
        width,
        y,
        fonts,
        ("CNPJ/CPF/NIF", format_document(fields.tomador_doc)),
        ("IM", fields.tomador_im or "—"),
        ("", ""),
    )
    if fields.tomador_endereco:
        y = _kv(
            c,
            width,
            y,
            "Endereço",
            format_endereco_display(fields.tomador_endereco),
            fonts,
            value_maxlen=110,
            stacked=True,
        )
    return y - 0.12 * cm


def _draw_servico(c, width, y, fields, fonts) -> float:
    y = _block_title(c, width, y, "SERVIÇO PRESTADO", fonts)
    y = _kv_row(
        c,
        width,
        y,
        fonts,
        ("Cód. trib. nacional", fields.codigo_servico),
        ("Local da prestação", fields.local_prestacao),
        ("", ""),
    )
    y = _kv(c, width, y, "Descrição", fields.descricao_servico, fonts, value_maxlen=120, stacked=True)
    return y - 0.12 * cm


def _draw_valores(c, width, y, fields, fonts) -> float:
    y = _block_title(c, width, y, "VALORES", fonts)
    y = _kv_row(
        c,
        width,
        y,
        fonts,
        ("Valor do serviço", format_money_br(fields.valor_servico)),
        ("Valor ISSQN", format_money_br(fields.valor_iss)),
        ("", ""),
    )
    # Sombreamento campo valor líquido (NT §2.2.3)
    left = _MARGIN + 0.1 * cm
    usable = width - 2 * _MARGIN - 0.2 * cm
    c.setFillColor(_GRAY_HEADER)
    c.rect(left, y - 0.85 * cm, usable, 0.78 * cm, fill=1, stroke=0)
    c.setFillColor(black)
    y = _kv(
        c,
        width,
        y,
        "Valor líquido da NFS-e",
        format_money_br(fields.valor_liquido),
        fonts,
        stacked=True,
    )
    return y - 0.12 * cm


def _draw_complementares(c, width, y, fields, fonts) -> None:
    y = _block_title(c, width, y, "INFORMAÇÕES COMPLEMENTARES", fonts)
    fed = format_money_br(fields.approx_federais) if fields.approx_federais else "—"
    est = format_money_br(fields.approx_estaduais) if fields.approx_estaduais else "—"
    mun = format_money_br(fields.approx_municipais) if fields.approx_municipais else "—"
    trib = f"Federais: {fed} | Estaduais: {est} | Municipais: {mun}"
    sn = format_percent_br(fields.approx_sn_percent)
    if sn:
        trib = f"{trib} | Simples Nacional: {sn}"
    _kv(
        c,
        width,
        y,
        "Totais aproximados de tributos (Lei 12.741/2012)",
        trib,
        fonts,
        value_maxlen=120,
        stacked=True,
    )


def _block_title(c, width, y, title: str, fonts: dict[str, str]) -> float:
    left = _MARGIN + 0.1 * cm
    usable = width - 2 * _MARGIN - 0.2 * cm
    h = 0.48 * cm
    c.setFillColor(_GRAY_HEADER)
    c.setStrokeColor(black)
    c.setLineWidth(0.5)
    c.rect(left, y - h, usable, h, fill=1, stroke=1)
    c.setFillColor(black)
    c.setFont(fonts["title"], 8)
    c.drawString(left + 0.15 * cm, y - h + 0.14 * cm, title)
    return y - h - 0.18 * cm


def _kv(
    c,
    width,
    y,
    label: str,
    value: str,
    fonts: dict[str, str],
    *,
    value_maxlen: int = 95,
    stacked: bool | None = None,
) -> float:
    """Label + valor com folga vertical (evita colisão — autorizada e cancelada)."""
    left = _MARGIN + 0.2 * cm
    usable = width - 2 * _MARGIN - 0.4 * cm
    value_txt = _clip(value, value_maxlen)
    if not label:
        c.setFont(fonts["body"], 7)
        c.drawString(left, y, value_txt)
        return y - 0.42 * cm

    # Label longo ou stacked explícito → valor na linha de baixo.
    use_stack = stacked if stacked is not None else (
        len(label) > 28 or c.stringWidth(label, fonts["title"], 7) > 4.8 * cm
    )
    if use_stack:
        c.setFont(fonts["title"], 7)
        c.drawString(left, y, label)
        c.setFont(fonts["body"], 8)
        c.drawString(left, y - 0.36 * cm, value_txt)
        return y - 0.72 * cm

    c.setFont(fonts["title"], 7)
    c.drawString(left, y, label)
    c.setFont(fonts["body"], 8)
    c.drawString(left + 5.4 * cm, y, value_txt)
    return y - 0.48 * cm


def _kv_row(c, width, y, fonts, *pairs: tuple[str, str]) -> float:
    left = _MARGIN + 0.2 * cm
    usable = width - 2 * _MARGIN - 0.4 * cm
    cols = [p for p in pairs if p[0] or p[1]]
    if not cols:
        return y
    col_w = usable / max(len(cols), 1)
    for i, (label, value) in enumerate(cols):
        x = left + i * col_w
        if label:
            c.setFont(fonts["title"], 6)
            c.drawString(x, y, label)
            c.setFont(fonts["body"], 8)
            c.drawString(x, y - 0.38 * cm, _clip(value, 32))
    return y - 0.78 * cm


def _draw_cancelled_watermark(c, width, height, fonts) -> None:
    """Marca d'água diagonal K35 atrás do texto (NT §2.5.1)."""
    c.saveState()
    # Cinza K35 com alfa — permanece legível sob títulos/valores.
    c.setFillColor(Color(0.65, 0.65, 0.65, alpha=0.45))
    c.setFont(fonts["title"], 48)
    c.translate(width / 2, height / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, "CANCELADA")
    c.restoreState()


def _qr_image(payload: str):
    from reportlab.lib.utils import ImageReader

    qr = qrcode.QRCode(version=None, box_size=8, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return ImageReader(bio)


def _format_chave(chave: str) -> str:
    digits = "".join(ch for ch in chave if ch.isdigit())
    if len(digits) == 50:
        return " ".join(digits[i : i + 5] for i in range(0, 50, 5))
    return chave


def _clip(value: str, max_len: int) -> str:
    value = value or ""
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def _draw_wrapped(
    c,
    text: str,
    *,
    x: float,
    y: float,
    max_width: float,
    font: str,
    size: int,
    leading: float,
    align: str = "left",
    center_x: float | None = None,
) -> None:
    c.setFont(font, size)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if c.stringWidth(trial, font, size) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    cy = y
    for line in lines[:3]:
        if align == "center" and center_x is not None:
            c.drawCentredString(center_x, cy, line)
        else:
            c.drawString(x, cy, line)
        cy -= leading


def xml_is_well_formed(xml_bytes: bytes) -> bool:
    try:
        safe_fromstring(xml_bytes)
        return True
    except Exception:  # noqa: BLE001 — lxml XMLSyntaxError e similares
        return False
