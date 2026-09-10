"""DANFE PDF — ponto de entrada (delega ao renderer MOC v2)."""

from __future__ import annotations

from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, render_danfe_moc_pdf


def render_danfe_pdf(
    xml_bytes: bytes,
    *,
    cancelled: bool = False,
    logo_bytes: bytes | None = None,
) -> bytes:
    return render_danfe_moc_pdf(xml_bytes, cancelled=cancelled, logo_bytes=logo_bytes)
