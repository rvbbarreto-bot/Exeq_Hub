"""nfeProc — wrap NFe + protNFe (MOC v4.00)."""

from __future__ import annotations

from integrations.sefaz_nfe.nfe_proc import (
    authorized_xml_bytes,
    build_synthetic_prot_nfe,
    extract_prot_nfe_xml,
    wrap_nfe_proc,
)
from integrations.sefaz_nfe.tests.test_http_emit_i4 import _FIXTURE_AUTORIZADA
from integrations.sefaz_nfe.xml_nfe import build_nfe_xml

_SNAP = {
    "emitente": {
        "cnpj": "37229907000137",
        "ie": "123456789",
        "name": "EXEQ LAB",
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
    "destinatario": {
        "document": "12345678909",
        "document_type": "cpf",
        "name": "Cliente",
        "address": {
            "logradouro": "Av B",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    },
    "header": {
        "nature": "VENDA",
        "series": 1,
        "number": 1,
        "tp_amb": "2",
        "issue_date": "2026-08-05",
        "ind_ie_dest": "9",
    },
    "items": [
        {
            "line": 1,
            "code": "SKU1",
            "description": "Produto",
            "ncm": "21069090",
            "cfop": "5102",
            "unit": "UN",
            "quantity": "1",
            "unit_price_cents": 1000,
            "taxes": {
                "icms": {"regime": "sn", "csosn": "102"},
                "pis": {"cst": "49"},
                "cofins": {"cst": "49"},
            },
        }
    ],
    "totals": {"products_cents": 1000, "total_cents": 1000},
    "payment": {"method": "99", "amount_cents": 1000},
}


def test_extract_prot_nfe_from_sefaz_response():
    prot = extract_prot_nfe_xml(_FIXTURE_AUTORIZADA)
    assert prot is not None
    assert b"infProt" in prot
    assert b"135260000000001" in prot


def test_wrap_nfe_proc_structure():
    nfe = build_nfe_xml(snapshot=_SNAP)
    prot = build_synthetic_prot_nfe(
        access_key="35260837229907000137550010000000011000000010",
        protocol="135260000000001",
        tp_amb="2",
    )
    proc = wrap_nfe_proc(signed_nfe_xml=nfe, prot_nfe_xml=prot)
    assert b"<nfeProc" in proc
    assert b'versao="4.00"' in proc
    assert proc.count(b"<NFe") >= 1
    assert b"<protNFe" in proc
    assert b"<infNFe" in proc


def test_authorized_xml_bytes_prefers_sefaz_prot():
    nfe = build_nfe_xml(snapshot=_SNAP)
    proc = authorized_xml_bytes(
        signed_nfe_xml=nfe,
        sefaz_body=_FIXTURE_AUTORIZADA,
    )
    assert proc is not None
    assert b"nfeProc" in proc
    assert b"135260000000001" in proc
