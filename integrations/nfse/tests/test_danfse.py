"""Testes G-PDF — DANFSe NT 008/2026 v1.02 (RF-41*, RF-43, RF-47) + polish M1."""

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from integrations.nfse.danfse import (
    LAYOUT_VERSION,
    evaluate_danfse_checklist,
    extract_danfse_fields,
    render_danfse_pdf,
)
from integrations.nfse.danfse.checklist import logo_asset_path
from integrations.nfse.danfse.fields import QR_BASE_URL

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_extract_fields_from_authorized_fixture():
    fields = extract_danfse_fields(_load("nfse_autorizada_minimal.xml"))
    assert fields.municipio_emitente == "Atibaia"
    assert fields.ambiente == "Homologação"
    assert fields.is_homologacao is True
    assert fields.numero == "123"
    assert len("".join(ch for ch in fields.chave_acesso if ch.isdigit())) == 50
    assert fields.prestador_doc == "12345678000190"
    assert fields.tomador_nome.startswith("TOMADOR")
    assert fields.codigo_servico == "010701"
    assert fields.valor_servico == "1500.00"
    assert fields.approx_federais == "45.00"
    assert fields.numero_dps == "1"
    assert fields.serie_dps == "900"
    assert fields.cancelled is False
    assert fields.situacao == "NFS-e Gerada"
    assert fields.qr_payload.startswith(QR_BASE_URL)
    assert LAYOUT_VERSION == "nt008-v1.06"


def test_extract_fields_from_prod_sample():
    fields = extract_danfse_fields(_load("nfse_autorizada_prod_sample.xml"))
    assert fields.ambiente == "Produção"
    assert fields.is_homologacao is False
    assert fields.numero == "68"
    assert fields.prestador_nome.startswith("EXEQ")
    assert fields.prestador_doc == "37229907000137"
    assert fields.prestador_email == "RIICARDO84@HOTMAIL.COM"
    assert fields.op_simp_nac == "Optante — ME/EPP"
    assert fields.trib_issqn == "Operação Tributável"
    assert fields.tp_ret_issqn == "Não Retido"
    assert fields.amb_gerador == "Sistema Nacional NFS-e"
    assert "JOSE FLORIDO" in fields.prestador_endereco.upper().replace("É", "E")
    assert "Spike" in fields.tomador_endereco or "Rua Spike" in fields.tomador_endereco
    assert fields.tomador_nome.startswith("MARIA")
    assert fields.codigo_servico == "170101"
    assert fields.valor_servico == "15.00"
    assert fields.valor_liquido == "15.00"
    assert fields.approx_sn_percent == "6.00"
    assert fields.local_prestacao == "Atibaia"
    assert len("".join(ch for ch in fields.chave_acesso if ch.isdigit())) == 50


def test_extract_cnbs_from_nested_cserv():
    fields = extract_danfse_fields(_load("nfse_autorizada_with_nbs.xml"))
    assert fields.codigo_nbs == "115013000"
    assert fields.codigo_servico == "010701"
    pdf = render_danfse_pdf(_load("nfse_autorizada_with_nbs.xml"))
    reader = PdfReader(BytesIO(pdf))
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "1.1501.30.00" in text


def test_official_logo_asset_present():
    path = logo_asset_path()
    assert path.is_file()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_authorized_pdf_a4_single_page_with_qr_metadata():
    pdf = render_danfse_pdf(_load("nfse_autorizada_minimal.xml"))
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    box = page.mediabox
    assert float(box.width) >= 590
    assert float(box.height) >= 835
    meta = reader.metadata or {}
    subject = str(meta.get("/Subject") or meta.subject or "")
    assert LAYOUT_VERSION in subject
    text = page.extract_text() or ""
    assert "DANFSe v2.0" in text
    assert "Documento Auxiliar da NFS-e" in text
    assert "NFS-e SEM VALIDADE JURÍDICA" in text
    assert "Atibaia" in text
    assert "Homologação" in text
    assert "PRESTADOR EXEQ LAB" in text
    assert "01.07.01" in text or "010701" in text
    assert "TRIBUTAÇÃO MUNICIPAL" in text.upper() or "ISSQN" in text
    assert "IBS" in text and "CBS" in text
    assert "VALOR TOTAL" in text.upper()
    assert "R$ 1.500,00" in text
    assert "IDENTIFICA" in text
    assert "PRESTADOR" in text
    assert "TOMADOR" in text
    assert "12.345.678/0001-90" in text
    resources = page.get("/Resources") or {}
    xobject = resources.get("/XObject") if resources else None
    assert xobject is not None
    assert len(xobject) >= 2  # logo + QR


def test_render_cancelled_has_ptbr_and_spacing_labels():
    pdf = render_danfse_pdf(_load("nfse_cancelada_minimal.xml"), cancelled=True)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "CANCELADA" in text
    assert "Cancelada" in text
    assert "R$" in text
    assert "PRESTADOR" in text
    assert "TOMADOR" in text
    assert "IDENTIFICA" in text.upper() or "IDENTIFICAÇÃO" in text


def test_cancelled_flag_forces_situacao_even_if_cstat_authorized():
    """PDF cancelada a partir do XML autorizado (cStat 100) deve exibir Situação Cancelada."""
    fields = extract_danfse_fields(_load("nfse_autorizada_minimal.xml"), cancelled=True)
    assert fields.cancelled is True
    assert fields.situacao == "Cancelada"
    pdf = render_danfse_pdf(_load("nfse_autorizada_minimal.xml"), cancelled=True)
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "Cancelada" in text
    assert "CANCELADA" in text


def test_cancelled_inferred_from_cstat_without_flag():
    fields = extract_danfse_fields(_load("nfse_cancelada_minimal.xml"))
    assert fields.cancelled is True
    assert fields.situacao == "Cancelada"
    pdf = render_danfse_pdf(_load("nfse_cancelada_minimal.xml"))
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text() or ""
    assert "CANCELADA" in text


def test_m1_field_coverage_at_least_80_percent():
    required = [
        "municipio_emitente",
        "ambiente",
        "numero",
        "chave_acesso",
        "data_emissao",
        "competencia",
        "prestador_nome",
        "prestador_doc",
        "tomador_nome",
        "tomador_doc",
        "descricao_servico",
        "codigo_servico",
        "valor_servico",
        "valor_iss",
        "valor_liquido",
        "numero_dps",
        "serie_dps",
        "prestador_endereco",
        "local_prestacao",
    ]
    fields = extract_danfse_fields(_load("nfse_autorizada_minimal.xml"))
    present = sum(1 for name in required if getattr(fields, name) not in {"", "—"})
    coverage = present / len(required)
    assert coverage >= 0.80, f"cobertura={coverage:.0%} presente={present}/{len(required)}"


def test_m1_visual_checklist_at_least_80_percent():
    result = evaluate_danfse_checklist(_load("nfse_autorizada_minimal.xml"))
    failed = [k for k, v in result.passed.items() if not v]
    assert result.ok_m1, f"cobertura={result.coverage:.0%} falhas={failed}"
    assert result.coverage >= 0.80


def test_m1_checklist_on_prod_sample_at_least_80_percent():
    result = evaluate_danfse_checklist(_load("nfse_autorizada_prod_sample.xml"))
    failed = [k for k, v in result.passed.items() if not v]
    assert result.ok_m1, f"cobertura={result.coverage:.0%} falhas={failed}"
    assert result.coverage >= 0.80
    assert result.passed["ambiente"]
    text = __import__("pypdf").PdfReader(
        __import__("io").BytesIO(
            render_danfse_pdf(_load("nfse_autorizada_prod_sample.xml"))
        )
    ).pages[0].extract_text() or ""
    assert "Produção" in text
    assert "Simples Nacional" in text or "6.00" in text
    assert "EXEQ" in text


def test_m1_checklist_cancelled():
    result = evaluate_danfse_checklist(_load("nfse_cancelada_minimal.xml"), cancelled=True)
    assert result.passed["watermark_cancelada"]
    assert result.ok_m1


def test_m4_visual_checklist_at_least_95_percent():
    """Meta Trilha B pós-M1 — cobertura visual ≥95% (Plano QA)."""
    for name in (
        "nfse_autorizada_minimal.xml",
        "nfse_autorizada_prod_sample.xml",
        "nfse_cancelada_minimal.xml",
    ):
        result = evaluate_danfse_checklist(
            _load(name), cancelled="cancel" in name
        )
        failed = [k for k, v in result.passed.items() if not v]
        assert result.ok_m4, f"{name} cobertura={result.coverage:.0%} falhas={failed}"
