"""DANFE NFC-e cupom PDF — render mínimo."""

from __future__ import annotations

from integrations.sefaz_nfe.danfe_nfce import LAYOUT_VERSION, render_danfce_pdf
from integrations.sefaz_nfe.xml_nfce import build_nfce_xml


def _sample_xml() -> bytes:
    return build_nfce_xml(
        snapshot={
            "document_model": "65",
            "emitente": {
                "cnpj": "37229907000137",
                "name": "EXEQ PDV",
                "ie": "ISENTO",
                "crt": "simples_nacional",
                "address": {
                    "logradouro": "Rua A",
                    "numero": "1",
                    "bairro": "Centro",
                    "municipio": "Atibaia",
                    "uf": "SP",
                    "cep": "12942480",
                    "codigo_ibge": "3504107",
                },
            },
            "header": {
                "model": "65",
                "nature": "VENDA",
                "series": 1,
                "number": 42,
                "tp_amb": "2",
                "issue_date": "2026-09-04",
                "omit_dest": True,
                "csc_id": "1",
                "csc_token": "HOMOLOGCSC",
            },
            "sefaz": {"csc_id": "1", "csc_token": "HOMOLOGCSC"},
            "items": [
                {
                    "line": 1,
                    "code": "SKU1",
                    "description": "Cafe",
                    "ncm": "21069090",
                    "cfop": "5102",
                    "unit": "UN",
                    "quantity": "2",
                    "unit_price_cents": 500,
                    "total_cents": 1000,
                    "origin": "0",
                    "csosn": "102",
                    "taxes": {"icms": {"regime": "sn", "csosn": "102"}},
                }
            ],
            "totals": {
                "products_cents": 1000,
                "total_cents": 1000,
                "icms_cents": 0,
                "pis_cents": 0,
                "cofins_cents": 0,
            },
            "payment": {"method": "99", "amount_cents": 1000},
        }
    )


def test_danfce_pdf_starts_with_pdf_header():
    pdf = render_danfce_pdf(_sample_xml())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_danfce_pdf_cancelled_banner():
    xml = _sample_xml()
    pdf = render_danfce_pdf(xml, cancelled=True)
    assert pdf.startswith(b"%PDF")


def test_danfce_layout_version():
    assert LAYOUT_VERSION == "exeq-danfce-0.1"
