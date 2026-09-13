"""Renderização PDF DANFSe — NT 008 gov-parity compacto (1 página A4)."""

from __future__ import annotations

import io
from dataclasses import dataclass
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
    format_cep,
    format_codigo_trib_nacional,
    format_competencia,
    format_datetime_br,
    format_document,
    format_endereco_curto,
    format_ibge,
    format_money_br,
    format_percent_br,
)
from integrations.nfse.xml_safe import safe_fromstring

LAYOUT_VERSION = "nt008-v1.06"
_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO_PATH = _ASSETS / "logo_nfse_horizontal.png"

_GRAY_HEADER = Color(0.95, 0.95, 0.95)
_MARGIN = 0.28 * cm
_USABLE_PAD = 0.14 * cm

# Tipografia gov — layout top-down (Y = topo da faixa; evita invasão da barra cinza)
_FS_LABEL = 5
_FS_VALUE = 6.5
_FS_BLOCK = 6
_FS_HEADER = 8
_FS_SUB = 6
_LABEL_LEADING = 0.12 * cm
_LABEL_VALUE_GAP = 0.08 * cm
_ROW_PAD = 0.06 * cm
_BLOCK_H = 0.34 * cm
_BLOCK_PAD = 0.10 * cm


@dataclass
class _Ctx:
    c: canvas.Canvas
    width: float
    height: float
    y: float
    fonts: dict[str, str]
    cancelled: bool

    @property
    def left(self) -> float:
        return _MARGIN + _USABLE_PAD

    @property
    def usable(self) -> float:
        return self.width - 2 * _MARGIN - 2 * _USABLE_PAD


def render_danfse_pdf(xml_bytes: bytes, *, cancelled: bool = False) -> bytes:
    fields = extract_danfse_fields(xml_bytes, cancelled=cancelled)
    fonts = _fonts()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setTitle(f"DANFSe v2.0 — {fields.numero}")
    c.setSubject(f"danfse_layout_version={LAYOUT_VERSION}")
    c.setCreator("EXEQ Hub")
    c.setStrokeColor(black)
    c.setLineWidth(1)
    c.rect(_MARGIN, _MARGIN, width - 2 * _MARGIN, height - 2 * _MARGIN)
    if fields.cancelled:
        _watermark(c, width, height, fonts)

    ctx = _Ctx(c=c, width=width, height=height, y=height - _MARGIN, fonts=fonts, cancelled=fields.cancelled)
    ctx.y = _header(ctx, fields)
    _section_identificacao(ctx, fields)
    _section_prestador(ctx, fields)
    _section_tomador(ctx, fields)
    _section_dest_inter(ctx, fields)
    _section_servico(ctx, fields)
    _section_trib_mun(ctx, fields)
    _section_trib_fed(ctx, fields)
    _section_trib_ibscbs(ctx, fields)
    _section_valores(ctx, fields)
    _section_complementares(ctx, fields)

    c.save()
    return buffer.getvalue()


@lru_cache(maxsize=1)
def _fonts() -> dict[str, str]:
    title, body = "Helvetica-Bold", "Helvetica"
    for regular, bold in (
        (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ):
        try:
            if regular.is_file() and bold.is_file():
                pdfmetrics.registerFont(TTFont("DanfseArial", str(regular)))
                pdfmetrics.registerFont(TTFont("DanfseArial-Bold", str(bold)))
                return {"title": "DanfseArial-Bold", "body": "DanfseArial"}
        except Exception:  # noqa: BLE001
            continue
    return {"title": title, "body": body}


def _header(ctx: _Ctx, f: DanfseFields) -> float:
    c, w, top = ctx.c, ctx.width, ctx.y
    left = ctx.left

    if _LOGO_PATH.is_file():
        lw, lh = 3.6 * cm, 0.72 * cm
        c.drawImage(str(_LOGO_PATH), left, top - 0.35 * cm - lh, width=lw, height=lh, mask="auto", preserveAspectRatio=True)

    c.setFont(ctx.fonts["title"], _FS_HEADER)
    c.drawCentredString(w / 2, top - 0.85 * cm, "DANFSe v2.0")
    c.setFont(ctx.fonts["body"], _FS_SUB)
    c.drawCentredString(w / 2, top - 1.12 * cm, "Documento Auxiliar da NFS-e")

    if f.is_homologacao:
        c.setFillColor(red)
        c.setFont(ctx.fonts["title"], 7)
        c.drawCentredString(w / 2, top - 1.38 * cm, "NFS-e SEM VALIDADE JURÍDICA")
        c.setFillColor(black)

    right = w - _MARGIN - _USABLE_PAD
    mun_line = f.municipio_emitente
    if f.prestador_uf:
        mun_line = f"{mun_line} - {f.prestador_uf}"
    c.setFont(ctx.fonts["body"], _FS_VALUE)
    c.drawRightString(right - 1.55 * cm, top - 0.75 * cm, mun_line)
    c.setFont(ctx.fonts["body"], _FS_LABEL)
    c.drawRightString(right - 1.55 * cm, top - 0.98 * cm, "Sistema Nacional NFS-e")
    c.drawRightString(right - 1.55 * cm, top - 1.18 * cm, f.ambiente)
    c.drawRightString(right - 1.55 * cm, top - 1.36 * cm, LAYOUT_VERSION)

    qr = 1.45 * cm
    qx = w - _MARGIN - qr - 0.05 * cm
    qy = top - 0.32 * cm - qr
    c.drawImage(_qr_image(f.qr_payload), qx, qy, width=qr, height=qr, mask="auto")
    cap = "A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR ou pela consulta da chave de acesso no portal nacional da NFS-e"
    _wrap(c, cap, x=qx - 0.15 * cm, y=qy - 0.10 * cm, w=qr + 0.25 * cm, font=ctx.fonts["body"], size=4.5, leading=5.5, cx=qx + qr / 2)

    chave_top = top - 1.55 * cm
    c.setFont(ctx.fonts["title"], _FS_LABEL)
    lb = chave_top - _ascent(ctx.fonts["title"], _FS_LABEL)
    c.drawString(left, lb, "N° NFS-e / CHAVE DE ACESSO DA NFS-e")
    c.setFont(ctx.fonts["body"], _FS_VALUE)
    chave_txt = f"{f.numero} / {''.join(ch for ch in f.chave_acesso if ch.isdigit())}"
    vb = lb - _LABEL_LEADING - _LABEL_VALUE_GAP - _ascent(ctx.fonts["body"], _FS_VALUE)
    c.drawString(left, vb, _truncate_width(c, chave_txt, qx - left - 0.15 * cm, ctx.fonts["body"], _FS_VALUE))

    chave_bottom = vb - _descent(ctx.fonts["body"], _FS_VALUE) - _ROW_PAD
    body_top = min(chave_bottom, qy - 0.58 * cm)
    return body_top


def _section_identificacao(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "IDENTIFICAÇÃO DA NFS-e")
    ctx.y = _grid(ctx, [
        ("NÚMERO DA NFS-e", f.numero),
        ("COMPETÊNCIA DA NFS-e", format_competencia(f.competencia)),
        ("DATA E HORA DA EMISSÃO DA NFS-e", format_datetime_br(f.data_emissao)),
        ("NÚMERO DA DPS", f.numero_dps),
        ("SÉRIE DA DPS", f.serie_dps),
        ("DATA E HORA DA EMISSÃO DA DPS", format_datetime_br(f.data_emissao_dps)),
        ("EMITENTE DA NFS-e", f.emitente_nfse),
        ("SITUAÇÃO DA NFS-e", f.situacao),
        ("FINALIDADE", f.finalidade),
        ("VERSÃO APLICATIVO", f.ver_aplic),
    ], cols=3)


def _section_prestador(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "PRESTADOR / FORNECEDOR")
    mun_uf = f"{f.prestador_municipio} / {f.prestador_uf}" if f.prestador_uf else f.prestador_municipio
    ibge_cep = " / ".join(
        p for p in (
            format_ibge(f.prestador_cmun) if f.prestador_cmun else "",
            format_cep(f.prestador_cep) if f.prestador_cep else "",
        ) if p
    ) or "—"
    ctx.y = _grid(ctx, [
        ("CNPJ / CPF / NIF", format_document(f.prestador_doc)),
        ("Indicador Municipal (Inscrição)", f.prestador_im),
        ("Telefone", f.prestador_fone or "—"),
        ("E-mail", f.prestador_email or "—"),
        ("Nome / Nome Empresarial", f.prestador_nome),
        ("Município / Sigla UF", mun_uf),
        ("Código IBGE / CEP", ibge_cep),
    ], cols=4)
    ctx.y = _full(ctx, "Endereço", format_endereco_curto(f.prestador_endereco))
    sn = f.op_simp_nac.replace("Optante — ", "Optante - ") if f.op_simp_nac else "—"
    ctx.y = _grid(ctx, [
        ("Simples Nacional na Data de Competência", sn),
        ("Regime de Apuração Tributária pelo SN", f.reg_ap_trib_sn or "—"),
    ], cols=2)


def _section_tomador(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "TOMADOR / ADQUIRENTE")
    if f.tomador_nome in {"", "—"} and f.tomador_doc in {"", "—"}:
        ctx.y = _full(ctx, "", "TOMADOR / ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
        return
    mun = f.tomador_municipio or format_ibge(f.tomador_cmun) if f.tomador_cmun else "—"
    mun_uf = f"{mun} / {f.tomador_uf}" if f.tomador_uf else mun
    ibge_cep = " / ".join(
        p for p in (
            format_ibge(f.tomador_cmun) if f.tomador_cmun else "",
            format_cep(f.tomador_cep) if f.tomador_cep else "",
        ) if p
    ) or "—"
    ctx.y = _grid(ctx, [
        ("CNPJ / CPF / NIF", format_document(f.tomador_doc)),
        ("Indicador Municipal (Inscrição)", f.tomador_im or "—"),
        ("Telefone", "—"),
        ("E-mail", f.tomador_email or "—"),
        ("Nome / Nome Empresarial", f.tomador_nome),
        ("Município / Sigla UF", mun_uf),
        ("Código IBGE / CEP", ibge_cep),
    ], cols=4)
    ctx.y = _full(ctx, "Endereço", format_endereco_curto(f.tomador_endereco or "—"))


def _section_dest_inter(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "DESTINATÁRIO / INTERMEDIÁRIO")
    dest = f.destinatario_nome or "DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e"
    inter = f.intermediario_nome or "INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e"
    ctx.y = _line(ctx, dest)
    ctx.y = _line(ctx, inter)


def _section_servico(ctx: _Ctx, f: DanfseFields) -> None:
    from apps.master_data.nbs_import import format_nbs_display_code

    ctx.y = _block(ctx, "SERVIÇO PRESTADO")
    cod = format_codigo_trib_nacional(f.codigo_servico)
    trib_mun = f.codigo_trib_municipal or "-"
    local = f.local_prestacao
    if f.local_prestacao_uf:
        local = f"{local} / {f.local_prestacao_uf} / -"
    nbs_display = format_nbs_display_code(f.codigo_nbs) if f.codigo_nbs else "—"
    ctx.y = _grid(ctx, [
        ("Código de Tributação Nacional/Municipal", f"{cod} / {trib_mun}"),
        ("Código da NBS", nbs_display),
        ("Local da Prestação / Sigla UF / País", local),
    ], cols=3)
    ctx.y = _full(ctx, "Descrição do Serviço", f.descricao_servico)


def _section_trib_mun(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "TRIBUTAÇÃO MUNICIPAL (ISSQN)")
    incid = f.municipio_incidencia
    if f.prestador_uf:
        incid = f"{incid} / {f.prestador_uf} / -"
    ctx.y = _grid(ctx, [
        ("Tipo de Tributação do ISSQN", f.trib_issqn),
        ("Município / Sigla UF / País de Incidência do ISSQN", incid),
        ("BC ISSQN", _dash(f.iss_bc)),
        ("Alíquota Aplicada", format_percent_br(f.iss_aliquota) or "—"),
        ("Retenção do ISSQN", f.tp_ret_issqn),
        ("ISSQN Apurado", _dash(f.iss_valor or f.valor_iss)),
    ], cols=3)


def _section_trib_fed(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "TRIBUTAÇÃO FEDERAL (EXCETO CBS)")
    ctx.y = _grid(ctx, [
        ("IRRF", _dash(f.irrf)),
        ("Contribuição Previdenciária - Retida", _dash(f.inss)),
        ("PIS - Débito Apuração Própria", _dash(f.pis)),
        ("COFINS - Débito Apuração Própria", _dash(f.cofins)),
        ("Contribuições Sociais - Retidas", _dash(f.csll)),
    ], cols=5)


def _section_trib_ibscbs(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "TRIBUTAÇÃO IBS/CBS")
    cst_class = f"{f.cst_ibs_cbs or '-'} / {f.c_class_trib or '-'}"
    ctx.y = _grid(ctx, [
        ("CST / cClassTrib", cst_class),
        ("Indicador de Operação", f.c_ind_op or "—"),
        ("Base de Cálculo Após Exclusões e Reduções", _dash(f.ibs_bc)),
        ("Alíquota - IBS UF / IBS Mun", f"{format_percent_br(f.ibs_aliq_uf) or '-'} / {format_percent_br(f.ibs_aliq_mun) or '-'}"),
        ("Valor Total Apurado - IBS", _dash(f.ibs_valor)),
        ("Alíquota - CBS", format_percent_br(f.cbs_aliquota) or "—"),
        ("Valor Total Apurado - CBS", _dash(f.cbs_valor)),
        ("Total do IBS/CBS", "R$ 0,00"),
    ], cols=4)


def _section_valores(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "VALOR TOTAL DA NFS-e")
    ctx.y = _grid(ctx, [
        ("VALOR DA OPERAÇÃO / SERVIÇO", _money(f.valor_servico)),
        ("Desconto Incondicionado", _dash(f.desconto_incond)),
        ("Desconto Condicionado", _dash(f.desconto_cond)),
        ("Total das Retenções (ISSQN / Federais)", "—"),
    ], cols=4)
    left, usable = ctx.left, ctx.usable
    rh = _row_height(ctx, extra_label_lines=0)
    ctx.c.setFillColor(_GRAY_HEADER)
    ctx.c.rect(left - 0.04 * cm, ctx.y - rh, usable + 0.08 * cm, rh - 0.02 * cm, fill=1, stroke=0)
    ctx.c.setFillColor(black)
    ctx.y = _grid(ctx, [
        ("VALOR LÍQUIDO DA NFS-e", _money(f.valor_liquido)),
        ("VALOR LÍQUIDO DA NFS-e + IBS/CBS", "R$ 0,00"),
    ], cols=2)


def _section_complementares(ctx: _Ctx, f: DanfseFields) -> None:
    ctx.y = _block(ctx, "INFORMAÇÕES COMPLEMENTARES")
    parts: list[str] = []
    if f.informacoes_complementares:
        parts.append(f.informacoes_complementares)
    sn = format_percent_br(f.approx_sn_percent)
    trib_txt = "Totais aproximados dos Tributos cfe. Lei n° 12.741/2012: Federais: -; Estaduais: -; Municipais: -;"
    if sn:
        trib_txt = f"{trib_txt} Simples Nacional: {sn}"
    parts.append(trib_txt)
    _full(ctx, "", " ".join(parts))


def _ascent(font: str, size: float) -> float:
    try:
        return pdfmetrics.getAscent(font) / 1000.0 * size
    except Exception:  # noqa: BLE001
        return size * 0.72


def _descent(font: str, size: float) -> float:
    try:
        return abs(pdfmetrics.getDescent(font)) / 1000.0 * size
    except Exception:  # noqa: BLE001
        return size * 0.2


def _block(ctx: _Ctx, title: str) -> float:
    """Desenha barra de seção; ctx.y passa a ser o TOPO da área de conteúdo abaixo."""
    c, y_top, left, usable = ctx.c, ctx.y, ctx.left, ctx.usable
    block_bottom = y_top - _BLOCK_H
    c.setFillColor(_GRAY_HEADER)
    c.setStrokeColor(black)
    c.setLineWidth(0.4)
    c.rect(left - 0.04 * cm, block_bottom, usable + 0.08 * cm, _BLOCK_H, fill=1, stroke=1)
    c.setFillColor(black)
    c.setFont(ctx.fonts["title"], _FS_BLOCK)
    title_baseline = block_bottom + (_BLOCK_H - _ascent(ctx.fonts["title"], _FS_BLOCK)) / 2 + 0.02 * cm
    c.drawString(left + 0.06 * cm, title_baseline, title)
    ctx.y = block_bottom - _BLOCK_PAD
    return ctx.y


def _label_block_height(ctx: _Ctx | None = None, *, extra_label_lines: int = 0) -> float:
    font = ctx.fonts["title"] if ctx else "DanfseArial-Bold"
    n = 1 + extra_label_lines
    return _ascent(font, _FS_LABEL) + (n - 1) * _LABEL_LEADING + _descent(font, _FS_LABEL) * 0.35


def _row_height(ctx: _Ctx | None = None, *, extra_label_lines: int = 0) -> float:
    body = ctx.fonts["body"] if ctx else "DanfseArial"
    return (
        _label_block_height(ctx, extra_label_lines=extra_label_lines)
        + _LABEL_VALUE_GAP
        + _ascent(body, _FS_VALUE)
        + _descent(body, _FS_VALUE) * 0.35
        + _ROW_PAD
    )


def _grid(ctx: _Ctx, cells: list[tuple[str, str]], *, cols: int) -> float:
    if not cells:
        return ctx.y
    left, usable, y_top = ctx.left, ctx.usable, ctx.y
    col_w = usable / cols
    row_cells = [cells[i : i + cols] for i in range(0, len(cells), cols)]
    for row in row_cells:
        max_extra = 0
        prepared: list[tuple[list[str], str]] = []
        for label, value in row:
            label_lines = _wrap_lines(
                ctx.c, label, col_w - 0.06 * cm, ctx.fonts["title"], _FS_LABEL, max_lines=2
            )
            max_extra = max(max_extra, len(label_lines) - 1)
            val = _truncate_width(ctx.c, value, col_w - 0.06 * cm, ctx.fonts["body"], _FS_VALUE)
            prepared.append((label_lines, val))

        rh = _row_height(ctx, extra_label_lines=max_extra)
        label_h = _label_block_height(ctx, extra_label_lines=max_extra)
        label_base = y_top - _ascent(ctx.fonts["title"], _FS_LABEL)
        val_base = y_top - label_h - _LABEL_VALUE_GAP - _ascent(ctx.fonts["body"], _FS_VALUE)

        for i, (label_lines, val) in enumerate(prepared):
            x = left + i * col_w
            for li, ll in enumerate(label_lines):
                ctx.c.setFont(ctx.fonts["title"], _FS_LABEL)
                ctx.c.drawString(x, label_base - li * _LABEL_LEADING, ll)
            ctx.c.setFont(ctx.fonts["body"], _FS_VALUE)
            ctx.c.drawString(x, val_base, val)

        y_top -= rh
    ctx.y = y_top
    return y_top


def _truncate_width(c, text: str, max_w: float, font: str, size: float) -> str:
    t = (text or "—").strip() or "—"
    c.setFont(font, size)
    if c.stringWidth(t, font, size) <= max_w:
        return t
    ell = "…"
    while t and c.stringWidth(t + ell, font, size) > max_w:
        t = t[:-1]
    return (t + ell) if t else ell


def _full(ctx: _Ctx, label: str, value: str) -> float:
    y_top, left, usable = ctx.y, ctx.left, ctx.usable
    if label:
        lb = y_top - _ascent(ctx.fonts["title"], _FS_LABEL)
        ctx.c.setFont(ctx.fonts["title"], _FS_LABEL)
        ctx.c.drawString(left, lb, label)
        vb = y_top - _label_block_height(ctx) - _LABEL_VALUE_GAP - _ascent(ctx.fonts["body"], _FS_VALUE)
    else:
        vb = y_top - _ascent(ctx.fonts["body"], _FS_VALUE)
    ctx.c.setFont(ctx.fonts["body"], _FS_VALUE)
    ctx.c.drawString(left, vb, _truncate_width(ctx.c, value, usable, ctx.fonts["body"], _FS_VALUE))
    ctx.y = vb - _descent(ctx.fonts["body"], _FS_VALUE) - _ROW_PAD
    return ctx.y


def _line(ctx: _Ctx, text: str) -> float:
    y_top = ctx.y
    vb = y_top - _ascent(ctx.fonts["body"], _FS_VALUE)
    ctx.c.setFont(ctx.fonts["body"], _FS_VALUE)
    ctx.c.drawString(ctx.left, vb, _truncate_width(ctx.c, text, ctx.usable, ctx.fonts["body"], _FS_VALUE))
    ctx.y = vb - _descent(ctx.fonts["body"], _FS_VALUE) - _ROW_PAD
    return ctx.y


def _fit(text: str, max_chars: int, *, font: str = "DanfseArial") -> str:
    t = (text or "—").strip() or "—"
    if len(t) <= max_chars:
        return t
    return t[: max(1, max_chars - 1)] + "…"


def _dash(v: str) -> str:
    return "—" if not v or v in {"—", "-"} else _money(v)


def _money(v: str) -> str:
    if not v or v in {"—", "-"}:
        return "—"
    return format_money_br(v)


def _watermark(c, w, h, fonts) -> None:
    c.saveState()
    c.setFillColor(Color(0.65, 0.65, 0.65, alpha=0.45))
    c.setFont(fonts["title"], 44)
    c.translate(w / 2, h / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, "CANCELADA")
    c.restoreState()


def _qr_image(payload: str):
    from reportlab.lib.utils import ImageReader

    qr = qrcode.QRCode(version=None, box_size=6, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return ImageReader(bio)


def _wrap_lines(c, text: str, max_w: float, font: str, size: float, *, max_lines: int = 3) -> list[str]:
    c.setFont(font, size)
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if c.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _truncate_width(c, lines[-1], max_w, font, size)
    return lines


def _wrap(c, text, *, x, y, w, font, size, leading, cx=None) -> None:
    c.setFont(font, size)
    words, cur, lines = text.split(), "", []
    for word in words:
        trial = f"{cur} {word}".strip()
        if c.stringWidth(trial, font, size) <= w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    cy = y
    for line in lines[:3]:
        if cx is not None:
            c.drawCentredString(cx, cy, line)
        else:
            c.drawString(x, cy, line)
        cy -= leading


def xml_is_well_formed(xml_bytes: bytes) -> bool:
    try:
        safe_fromstring(xml_bytes)
        return True
    except Exception:  # noqa: BLE001
        return False
