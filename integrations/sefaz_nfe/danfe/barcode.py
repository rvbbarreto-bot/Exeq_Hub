"""Code 128C — payload = chave 44 dígitos (§8)."""

from __future__ import annotations

from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.shapes import Drawing

from integrations.sefaz_nfe.danfe.formatters import digits_only


def access_key_barcode_drawing(
    access_key: str,
    *,
    bar_height_mm: float = 8.0,
) -> Drawing:
    """
    Gera Code128 com payload numérico de 44 dígitos.
    ReportLab seleciona subset; entrada somente dígitos favorece 128C.
    """
    from integrations.sefaz_nfe.danfe.layout import mm_to_pt

    key = digits_only(access_key)
    if len(key) != 44:
        raise ValueError("chave de acesso deve ter 44 dígitos para barcode")
    bar_h = mm_to_pt(bar_height_mm)
    return createBarcodeDrawing(
        "Code128",
        value=key,
        barHeight=bar_h,
        barWidth=0.32,
        humanReadable=False,
        quiet=1,
    )


def barcode_payload(access_key: str) -> str:
    return digits_only(access_key)
