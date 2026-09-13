"""Checklist automatizado DANFE Modelo 55 — QA Phase 4."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from integrations.sefaz_nfe.danfe.barcode import barcode_payload
from integrations.sefaz_nfe.danfe.formatters import digits_only, format_access_key
from integrations.sefaz_nfe.danfe.layout import A4_PORTRAIT, mm_to_pt
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, render_danfe_moc_pdf
from integrations.sefaz_nfe.danfe.viewmodel import build_danfe_viewmodel

CHECKLIST_ITEMS = (
    "pdf_valido",
    "a4_portrait",
    "layout_version",
    "titulo_danfe",
    "subtitulo_danfe",
    "canhoto_primeira_pagina",
    "chave_acesso_44",
    "chave_no_pdf",
    "barcode_payload",
    "protocolo_ou_contingencia",
    "emitente_presente",
    "destinatario_presente",
    "grid_produtos",
    "issqn_bloco",
    "totais_imposto",
    "informacoes_complementares_bloco",
    "homolog_sem_valor_fiscal",
    "watermark_cancelada",
    "paginacao_folha",
    "cabecalho_p2_emitente",
    "fatura_estruturada",
    "transporte_estruturado",
)


@dataclass(frozen=True)
class ChecklistResult:
    passed: dict[str, bool]
    coverage: float
    page_count: int = 0

    @property
    def ok(self) -> bool:
        required = (
            "pdf_valido",
            "a4_portrait",
            "chave_acesso_44",
            "chave_no_pdf",
            "titulo_danfe",
        )
        return all(self.passed.get(k) for k in required) and self.coverage >= 0.75


def evaluate_danfe_checklist(xml_bytes: bytes, *, cancelled: bool = False) -> ChecklistResult:
    from pypdf import PdfReader

    vm = build_danfe_viewmodel(xml_bytes, cancelled=cancelled)
    pdf = render_danfe_moc_pdf(xml_bytes, cancelled=cancelled or vm.cancelled)
    reader = PdfReader(BytesIO(pdf))
    page_count = len(reader.pages)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    box = reader.pages[0].mediabox
    w_pt = float(box.width)
    h_pt = float(box.height)
    key_fmt = format_access_key(vm.access_key)
    key_digits = digits_only(vm.access_key)

    checks = {
        "pdf_valido": pdf.startswith(b"%PDF"),
        "a4_portrait": abs(w_pt - mm_to_pt(A4_PORTRAIT.width_mm)) < 4
        and abs(h_pt - mm_to_pt(A4_PORTRAIT.height_mm)) < 4,
        "layout_version": LAYOUT_VERSION in (reader.metadata.get("/Subject") or "")
        or LAYOUT_VERSION in text,
        "titulo_danfe": "DANFE" in text,
        "subtitulo_danfe": "DOCUMENTO AUXILIAR" in text.upper(),
        "canhoto_primeira_pagina": "RECEBEMOS DE" in text,
        "chave_acesso_44": len(key_digits) == 44,
        "chave_no_pdf": key_fmt in text or key_digits in text.replace(" ", ""),
        "barcode_payload": len(barcode_payload(vm.access_key)) == 44,
        "protocolo_ou_contingencia": bool(vm.authorization.protocol)
        or vm.authorization.is_contingency
        or vm.tp_amb == "2",
        "emitente_presente": vm.emit_name and vm.emit_name.split()[0] in text,
        "destinatario_presente": "DESTINATÁRIO" in text.upper() or vm.dest_name[:4] in text,
        "grid_produtos": "DESCRI" in text.upper() or "COD" in text,
        "issqn_bloco": "ISSQN" in text.upper(),
        "totais_imposto": "CÁLCULO DO IMPOSTO" in text.upper() or "V. NF" in text,
        "informacoes_complementares_bloco": "INFORMAÇÕES COMPLEMENTARES" in text.upper(),
        "homolog_sem_valor_fiscal": (vm.tp_amb != "2") or ("SEM VALOR FISCAL" in text.upper()),
        "watermark_cancelada": (not (cancelled or vm.cancelled)) or ("CANCELADA" in text),
        "paginacao_folha": f"FOLHA 1/{page_count}" in text.upper() or f"Folha 1/{page_count}" in text,
        "cabecalho_p2_emitente": page_count < 2
        or (vm.emit_name.split()[0] in (reader.pages[1].extract_text() or "")),
        "fatura_estruturada": "FATURA / DUPLICATAS" in text.upper(),
        "transporte_estruturado": "TRANSPORTADOR" in text.upper(),
    }
    passed_n = sum(1 for v in checks.values() if v)
    return ChecklistResult(
        passed=checks,
        coverage=passed_n / len(checks),
        page_count=page_count,
    )
