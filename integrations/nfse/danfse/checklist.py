"""Checklist visual / estrutural M1/M4 — NT 008/2026 v1.02 (Anexo I)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from integrations.nfse.danfse.fields import extract_danfse_fields
from integrations.nfse.danfse.formatters import (
    format_codigo_trib_nacional,
    format_competencia,
    format_money_br,
)
from integrations.nfse.danfse.render import LAYOUT_VERSION, _LOGO_PATH, render_danfse_pdf

CHECKLIST_ITEMS = (
    "pdf_valido",
    "pagina_unica_a4",
    "layout_version",
    "titulo_danfse_v2",
    "logo_oficial_embutida",
    "municipio_emitente",
    "ambiente",
    "homolog_sem_validade",
    "qr_code_presente",
    "chave_acesso",
    "numero_nfse",
    "competencia",
    "data_emissao",
    "situacao_nfse_gerada",
    "bloco_prestador",
    "bloco_tomador",
    "bloco_servico",
    "bloco_tributacao_municipal",
    "bloco_tributacao_federal",
    "bloco_tributacao_ibscbs",
    "bloco_valor_total",
    "valor_liquido",
    "totais_aproximados",
    "watermark_cancelada",
)


@dataclass(frozen=True)
class ChecklistResult:
    passed: dict[str, bool]
    coverage: float

    @property
    def ok_m1(self) -> bool:
        return self.coverage >= 0.80 and self.passed.get("pdf_valido", False)

    @property
    def ok_m4(self) -> bool:
        return self.coverage >= 0.95 and self.passed.get("pdf_valido", False)


def evaluate_danfse_checklist(xml_bytes: bytes, *, cancelled: bool = False) -> ChecklistResult:
    from io import BytesIO

    from pypdf import PdfReader

    fields = extract_danfse_fields(xml_bytes, cancelled=cancelled)
    pdf = render_danfse_pdf(xml_bytes, cancelled=cancelled or fields.cancelled)
    reader = PdfReader(BytesIO(pdf))
    page = reader.pages[0]
    text = page.extract_text() or ""
    resources = page.get("/Resources") or {}
    xobject = resources.get("/XObject") if resources else None
    xobj_count = len(xobject) if xobject is not None else 0
    box = page.mediabox
    meta = reader.metadata or {}
    subject = str(meta.get("/Subject") or getattr(meta, "subject", "") or "")

    has_totais = (
        "12.741" in text
        or "aproximados" in text.lower()
        or "Simples Nacional" in text
        or bool(fields.approx_federais or fields.approx_sn_percent)
    )
    codigo_fmt = format_codigo_trib_nacional(fields.codigo_servico)
    checks = {
        "pdf_valido": pdf.startswith(b"%PDF"),
        "pagina_unica_a4": len(reader.pages) == 1
        and float(box.width) >= 590
        and float(box.height) >= 835,
        "layout_version": LAYOUT_VERSION in subject or LAYOUT_VERSION in text,
        "titulo_danfse_v2": "DANFSe v2.0" in text,
        "logo_oficial_embutida": _LOGO_PATH.is_file() and xobj_count >= 2,
        "municipio_emitente": fields.municipio_emitente not in {"", "—"}
        and fields.municipio_emitente in text,
        "ambiente": fields.ambiente in text,
        "homolog_sem_validade": (not fields.is_homologacao)
        or ("SEM VALIDADE JURÍDICA" in text),
        "qr_code_presente": xobj_count >= 1,
        "chave_acesso": fields.chave_acesso not in {"", "—"},
        "numero_nfse": fields.numero not in {"", "—"} and fields.numero in text,
        "competencia": fields.competencia not in {"", "—"}
        and (
            fields.competencia in text
            or format_competencia(fields.competencia) in text
        ),
        "data_emissao": fields.data_emissao not in {"", "—"},
        "situacao_nfse_gerada": (cancelled or fields.cancelled)
        or ("NFS-e Gerada" in text or "Cancelada" in text),
        "bloco_prestador": "PRESTADOR" in text and fields.prestador_nome.split()[0] in text,
        "bloco_tomador": "TOMADOR" in text,
        "bloco_servico": "SERVI" in text
        and (fields.codigo_servico in text or codigo_fmt in text),
        "bloco_tributacao_municipal": "TRIBUTAÇÃO MUNICIPAL" in text.upper()
        or "ISSQN" in text,
        "bloco_tributacao_federal": "TRIBUTAÇÃO FEDERAL" in text.upper()
        or "IRRF" in text,
        "bloco_tributacao_ibscbs": "IBS" in text and "CBS" in text,
        "bloco_valor_total": "VALOR TOTAL" in text.upper(),
        "valor_liquido": fields.valor_liquido not in {"", "—"}
        and (
            fields.valor_liquido in text
            or format_money_br(fields.valor_liquido) in text
        ),
        "totais_aproximados": has_totais,
        "watermark_cancelada": (not (cancelled or fields.cancelled))
        or ("CANCELADA" in text),
    }
    passed_n = sum(1 for v in checks.values() if v)
    return ChecklistResult(passed=checks, coverage=passed_n / len(checks))


def logo_asset_path() -> Path:
    return _LOGO_PATH
