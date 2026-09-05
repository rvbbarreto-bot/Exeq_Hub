"""NFC-e HTTP SEFAZ-SP — mock autorização (sem rede)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from integrations.sefaz_nfe.port import HttpNfeProvider
from integrations.sefaz_nfe.tests.test_http_emit_i4 import (
    _FIXTURE_AUTORIZADA,
    _passthrough_sign,
)
from integrations.sefaz_nfe.transport import SefazHttpResponse


def _nfce_snap(*, csc_token: str = "HOMOLOGCSC"):
    return {
        "document_model": "65",
        "emitente": {
            "cnpj": "37229907000137",
            "ie": "123",
            "name": "EXEQ PDV",
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
            "number": 1,
            "tp_amb": "2",
            "issue_date": "2026-09-04",
            "omit_dest": True,
            "csc_id": "1",
            "csc_token": csc_token,
        },
        "sefaz": {
            "csc_id": "1",
            "csc_token": csc_token,
            "qr_base_url": (
                "https://www.homologacao.nfce.fazenda.sp.gov.br/"
                "NFCeConsultaPublica/Paginas/ConsultaQRCode.aspx"
            ),
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
                "taxes": {
                    "icms": {"regime": "sn", "csosn": "102", "value_cents": 0},
                    "pis": {"cst": "07", "value_cents": 0},
                    "cofins": {"cst": "07", "value_cents": 0},
                },
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


def test_nfce_http_missing_csc():
    snap = _nfce_snap()
    snap["sefaz"] = {"csc_id": "1", "csc_token": ""}
    snap["header"]["csc_token"] = ""
    r = HttpNfeProvider().emitir(invoice_snapshot=snap, context={})
    assert r.status == "failed"
    assert r.rejection_code == "CSC"


@pytest.mark.django_db
def test_nfce_http_dry_run(settings, tenant_a):
    settings.NFCE_HTTP_DRY_RUN = True
    with patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")):
        with patch("integrations.sefaz_nfe.sign.sign_nfe_xml", side_effect=_passthrough_sign):
            r = HttpNfeProvider().emitir(
                invoice_snapshot=_nfce_snap(),
                context={"tenant": tenant_a},
            )
    assert r.status == "failed"
    assert r.rejection_code == "DRY_RUN"
    assert r.signed_xml is not None
    assert b"<mod>65</mod>" in r.signed_xml
    assert b"infNFeSupl" in r.signed_xml


@pytest.mark.django_db
def test_nfce_http_mock_authorized(settings, tenant_a):
    settings.NFCE_HTTP_DRY_RUN = False
    authorized = SefazHttpResponse(
        http_status=200,
        body=_FIXTURE_AUTORIZADA,
        c_stat="100",
        x_motivo="Autorizado o uso da NF-e",
        protocol="135260000000001",
        access_key="35260837229907000137550010000000011000000010",
        lote_c_stat="104",
    )
    posted: dict = {}

    def _capture_post(*, url, envi_nfe_xml, pfx_bytes, password="", timeout=60.0):
        posted["url"] = url
        posted["xml_len"] = len(envi_nfe_xml)
        return authorized

    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch("integrations.sefaz_nfe.sign.sign_nfe_xml", side_effect=_passthrough_sign),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_autorizacao",
            side_effect=_capture_post,
        ),
    ):
        r = HttpNfeProvider().emitir(
            invoice_snapshot=_nfce_snap(),
            context={"tenant": tenant_a},
        )

    assert r.status == "authorized"
    assert r.protocol == "135260000000001"
    assert posted["url"] == (
        "https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeAutorizacao4.asmx"
    )
    assert posted["xml_len"] > 100
    assert r.signed_xml is not None
    assert b"<mod>65</mod>" in r.signed_xml
