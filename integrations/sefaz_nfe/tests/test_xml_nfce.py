"""Golden-file básico — XML NFC-e mod 65."""

from __future__ import annotations

from integrations.sefaz_nfe.xml_nfce import build_nfce_xml


def _sample_snapshot(*, omit_dest: bool = True):
    dest = None
    if not omit_dest:
        dest = {"document": "39053344705", "name": "CONSUMIDOR", "document_type": "cpf"}
    return {
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
        "destinatario": dest,
        "header": {
            "model": "65",
            "nature": "VENDA",
            "series": 1,
            "number": 1,
            "tp_amb": "2",
            "issue_date": "2026-09-04",
            "omit_dest": omit_dest,
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
                "unit_price_cents": 10000,
                "total_cents": 10000,
                "origin": "0",
                "csosn": "102",
                "taxes": {"icms": {"regime": "sn", "csosn": "102"}},
            }
        ],
        "totals": {
            "products_cents": 10000,
            "total_cents": 10000,
            "icms_cents": 0,
            "pis_cents": 0,
            "cofins_cents": 0,
        },
        "payment": {"method": "99", "amount_cents": 10000},
    }


def test_xml_nfce_mod_65():
    xml = build_nfce_xml(snapshot=_sample_snapshot(omit_dest=True))
    text = xml.decode("utf-8")
    assert "<mod>65</mod>" in text
    assert "<tpImp>4</tpImp>" in text
    assert "<indFinal>1</indFinal>" in text
    assert "<indPres>1</indPres>" in text
    assert "<dest>" not in text
    assert "infNFeSupl" in text
    assert "qrCode" in text


def test_xml_nfce_with_cpf_dest():
    xml = build_nfce_xml(snapshot=_sample_snapshot(omit_dest=False))
    text = xml.decode("utf-8")
    assert "<dest>" in text
    assert "<CPF>" in text
