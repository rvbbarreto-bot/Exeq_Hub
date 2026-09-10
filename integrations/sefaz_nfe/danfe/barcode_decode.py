"""Decode Code128 da chave NF-e — PDF raster + zxing-cpp (§8 Phase 4)."""

from __future__ import annotations

import io
from typing import Any

from integrations.sefaz_nfe.danfe.formatters import digits_only

_DEFAULT_DPIS = (600, 500, 400)


def _pil_from_pixmap(pix: Any):
    from PIL import Image

    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def decode_barcodes_from_image(image: Any) -> list[str]:
    import zxingcpp

    out: list[str] = []
    for result in zxingcpp.read_barcodes(image):
        text = (result.text or "").strip()
        if text:
            out.append(text)
    return out


def _decode_from_image(img: Any) -> str | None:
    for text in decode_barcodes_from_image(img):
        key = digits_only(text)
        if len(key) == 44:
            return key
    from PIL import Image

    w, h = img.size
    if w > 0 and h > 0:
        upscaled = img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
        for text in decode_barcodes_from_image(upscaled):
            key = digits_only(text)
            if len(key) == 44:
                return key
    return None


def _decode_from_pixmap(pix: Any) -> str | None:
    return _decode_from_image(_pil_from_pixmap(pix))


def decode_access_key_from_pdf(
    pdf_bytes: bytes,
    *,
    dpi: int | None = None,
    page_index: int = 0,
) -> str | None:
    """Rasteriza página do PDF e decodifica Code128 com 44 dígitos."""
    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if page_index >= len(doc):
        return None

    dpis = (dpi,) if dpi else _DEFAULT_DPIS
    page = doc[page_index]
    for d in dpis:
        pix = page.get_pixmap(dpi=d, alpha=False)
        found = _decode_from_pixmap(pix)
        if found:
            return found
    return None


def decode_access_key_from_barcode_drawing(access_key: str, *, dpi: int | None = None) -> str | None:
    """
    Decodifica barcode isolado (PDF mínimo com Code128).
    Útil quando renderPM/Cairo não está disponível.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    from integrations.sefaz_nfe.danfe.barcode import access_key_barcode_drawing

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    bc = access_key_barcode_drawing(access_key)
    bc.drawOn(c, 40, 750)
    c.save()
    return decode_access_key_from_pdf(buf.getvalue(), dpi=dpi, page_index=0)
