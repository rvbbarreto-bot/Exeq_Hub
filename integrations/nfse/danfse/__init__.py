"""Gerador DANFSe (PDF) — NT SE/CGNFS-e 008/2026 v1.02. Render-only a partir do XML."""

from integrations.nfse.danfse.checklist import ChecklistResult, evaluate_danfse_checklist
from integrations.nfse.danfse.fields import DanfseFields, extract_danfse_fields
from integrations.nfse.danfse.render import LAYOUT_VERSION, render_danfse_pdf

__all__ = [
    "LAYOUT_VERSION",
    "ChecklistResult",
    "DanfseFields",
    "evaluate_danfse_checklist",
    "extract_danfse_fields",
    "render_danfse_pdf",
]
