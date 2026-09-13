"""PDF stub DAS/DARF com conteúdo legível (lab/QA — não é documento fiscal real)."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


def render_stub_guia_pdf(
    *,
    tipo: str,
    cnpj: str,
    competencia: str,
    valor_principal: Decimal,
    valor_multa: Decimal,
    valor_juros: Decimal,
    linha_digitavel: str,
    pix_copia_cola: str,
    data_vencimento: str | None,
) -> bytes:
    total = valor_principal + valor_multa + valor_juros
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _w, h = A4
    y = h - 2 * cm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, y, f"Guia {tipo} — STUB LAB EXEQ Hub")
    y -= 0.8 * cm

    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.55, 0, 0)
    c.drawString(2 * cm, y, "Documento simulado para homologacao. Nao valido para pagamento na Receita.")
    c.setFillColorRGB(0, 0, 0)
    y -= 1.2 * cm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, y, "Identificacao")
    y -= 0.6 * cm
    c.setFont("Helvetica", 10)
    for line in (
        f"CNPJ: {cnpj}",
        f"Competencia: {competencia}",
        f"Vencimento: {data_vencimento or '—'}",
    ):
        c.drawString(2 * cm, y, line)
        y -= 0.55 * cm

    y -= 0.4 * cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, y, "Valores")
    y -= 0.6 * cm
    c.setFont("Helvetica", 10)
    for label, val in (
        ("Principal", valor_principal),
        ("Multa", valor_multa),
        ("Juros", valor_juros),
        ("Total", total),
    ):
        c.drawString(2 * cm, y, f"{label}: R$ {val:.2f}")
        y -= 0.55 * cm

    y -= 0.4 * cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, y, "Pagamento")
    y -= 0.6 * cm
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, y, "Linha digitavel:")
    y -= 0.45 * cm
    c.setFont("Courier", 8)
    c.drawString(2 * cm, y, linha_digitavel or "—")
    y -= 0.8 * cm
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, y, "PIX copia e cola:")
    y -= 0.45 * cm
    pix = pix_copia_cola or "—"
    c.setFont("Courier", 7)
    max_chars = 90
    while pix:
        chunk, pix = pix[:max_chars], pix[max_chars:]
        c.drawString(2 * cm, y, chunk)
        y -= 0.4 * cm

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(2 * cm, 1.5 * cm, "Gerado por RECEITA_HTTP_MODE=stub — substituir por PDF SERPRO em producao.")
    c.save()
    return buf.getvalue()


# Legado: PDF vazio (nao usar — mantido so para referencia de tamanho minimo).
STUB_DAS_PDF = render_stub_guia_pdf(
    tipo="DAS",
    cnpj="00000000000191",
    competencia="2024-06",
    valor_principal=Decimal("150.75"),
    valor_multa=Decimal("0.00"),
    valor_juros=Decimal("0.00"),
    linha_digitavel="237930000000191202406",
    pix_copia_cola="00020126STUBDAS000000000001912024-06",
    data_vencimento="2024-07-10",
)
