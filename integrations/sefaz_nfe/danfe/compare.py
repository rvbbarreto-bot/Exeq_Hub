"""Comparação estrutural de PDF DANFE — Fase 2 (sem pixel diff)."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

# Frases obrigatórias MOC / ERP referência para smoke de regressão estrutural.
MOC_STRUCTURAL_MARKERS = (
    "DANFE",
    "DOCUMENTO AUXILIAR",
    "IDENTIFICAÇÃO DO EMITENTE",
    "DESTINATÁRIO",
    "CÁLCULO DO IMPOSTO",
    "ISSQN",
    "INFORMAÇÕES COMPLEMENTARES",
    "RESERVADO AO FISCO",
)


@dataclass(frozen=True)
class StructuralCompareResult:
    passed: dict[str, bool]
    missing: tuple[str, ...] = field(default_factory=tuple)
    page_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.missing


def pdf_page_texts(pdf_bytes: bytes) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    return [(p.extract_text() or "") for p in reader.pages]


def compare_structural(pdf_bytes: bytes, *, extra_markers: tuple[str, ...] = ()) -> StructuralCompareResult:
    """Verifica presença de marcadores textuais MOC no PDF."""
    texts = pdf_page_texts(pdf_bytes)
    combined = "\n".join(texts).upper()
    markers = MOC_STRUCTURAL_MARKERS + extra_markers
    passed = {m: m.upper() in combined for m in markers}
    missing = tuple(m for m, ok in passed.items() if not ok)
    return StructuralCompareResult(passed=passed, missing=missing, page_count=len(texts))
