"""Testes unitários integração SEFAZ NF-e (XML/chave/endpoints) — sem rede."""

from __future__ import annotations

from integrations.sefaz_nfe.access_key import build_access_key, check_digit_mod11
from integrations.sefaz_nfe.endpoints import resolve_endpoints
from integrations.sefaz_nfe.xml_nfe import build_nfe_xml


def test_access_key_length_and_dv():
    key = build_access_key(
        uf="SP",
        issue_date_iso="2026-08-05",
        cnpj="37229907000137",
        series=1,
        number=1,
        cnf=12345678,
    )
    assert len(key) == 44
    assert key.isdigit()
    assert key[-1] == check_digit_mod11(key[:43])
    assert key[:2] == "35"


def test_resolve_endpoints_sp_homolog():
    ep = resolve_endpoints(uf="SP", tp_amb="2")
    assert "homologacao" in ep.autorizacao
    assert ep.uf == "SP"


def test_build_nfe_xml_has_infNFe():
    snap = {
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
            "finality": "1",
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
                "quantity": "2",
                "unit_price_cents": 10000,
                "total_cents": 20000,
                "origin": "0",
                "csosn": "102",
                "taxes": {
                    "origin": "0",
                    "icms": {"regime": "sn", "csosn": "102", "value_cents": 0},
                    "pis": {"cst": "07", "value_cents": 0, "rate_bp": 0, "base_cents": 0},
                    "cofins": {"cst": "07", "value_cents": 0, "rate_bp": 0, "base_cents": 0},
                },
            }
        ],
        "totals": {
            "products_cents": 20000,
            "total_cents": 20000,
            "freight_cents": 0,
            "discount_cents": 0,
            "icms_cents": 0,
            "pis_cents": 0,
            "cofins_cents": 0,
        },
        "payment": {"method": "99", "amount_cents": 20000},
    }
    xml = build_nfe_xml(snapshot=snap)
    text = xml.decode("utf-8")
    assert "infNFe" in text
    assert "37229907000137" in text
    assert "ICMSSN102" in text
    assert "21069090" in text


def test_http_provider_fails_without_tenant():
    from integrations.sefaz_nfe.port import HttpNfeProvider

    r = HttpNfeProvider().emitir(
        invoice_snapshot={
            "emitente": {"cnpj": "37229907000137", "address": {"uf": "SP"}},
            "header": {"tp_amb": "2", "series": 1, "number": 1, "issue_date": "2026-08-05"},
            "items": [],
            "totals": {},
        },
        context={},
    )
    assert r.status == "failed"
    assert r.rejection_code == "CERT"
