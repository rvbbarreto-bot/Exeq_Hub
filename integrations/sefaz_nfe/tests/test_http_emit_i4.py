"""I4 — parse autorização + emit HTTP com mock (sem rede SEFAZ)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from integrations.sefaz_nfe.parse import (
    map_cstat_to_status,
    parse_autorizacao_response,
    sanitize_sefaz_raw,
)
from integrations.sefaz_nfe.port import HttpNfeProvider
from integrations.sefaz_nfe.transport import SefazHttpResponse, post_nfe_autorizacao

_FIXTURE_AUTORIZADA = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">
      <retEnviNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
        <tpAmb>2</tpAmb>
        <cStat>104</cStat>
        <xMotivo>Lote processado</xMotivo>
        <protNFe versao="4.00">
          <infProt>
            <tpAmb>2</tpAmb>
            <chNFe>35260837229907000137550010000000011000000010</chNFe>
            <dhRecbto>2026-08-05T12:00:00-03:00</dhRecbto>
            <nProt>135260000000001</nProt>
            <digVal>abc</digVal>
            <cStat>100</cStat>
            <xMotivo>Autorizado o uso da NF-e</xMotivo>
          </infProt>
        </protNFe>
      </retEnviNFe>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>
"""

_FIXTURE_REJEITADA = """<?xml version="1.0" encoding="UTF-8"?>
<retEnviNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <tpAmb>2</tpAmb>
  <cStat>104</cStat>
  <xMotivo>Lote processado</xMotivo>
  <protNFe versao="4.00">
    <infProt>
      <chNFe>35260837229907000137550010000000011000000011</chNFe>
      <cStat>204</cStat>
      <xMotivo>Rejeicao: Duplicidade de NF-e</xMotivo>
    </infProt>
  </protNFe>
</retEnviNFe>
"""

_FIXTURE_LOTE_RECEBIDO = """<?xml version="1.0" encoding="UTF-8"?>
<retEnviNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <tpAmb>2</tpAmb>
  <cStat>103</cStat>
  <xMotivo>Lote recebido com sucesso</xMotivo>
  <infRec>
    <nRec>123456789012345</nRec>
  </infRec>
</retEnviNFe>
"""


def test_parse_prefers_infprot_over_lote_104():
    p = parse_autorizacao_response(_FIXTURE_AUTORIZADA)
    assert p.c_stat == "100"
    assert p.lote_c_stat == "104"
    assert p.protocol == "135260000000001"
    assert p.access_key.startswith("35")
    assert "Autorizado" in p.x_motivo


def test_parse_rejeicao_204():
    p = parse_autorizacao_response(_FIXTURE_REJEITADA)
    assert p.c_stat == "204"
    assert "Duplicidade" in p.x_motivo
    assert map_cstat_to_status(p.c_stat) == "rejected"


def test_parse_lote_103_polling():
    p = parse_autorizacao_response(_FIXTURE_LOTE_RECEBIDO)
    assert p.c_stat == "103"
    assert p.n_rec == "123456789012345"
    assert map_cstat_to_status(p.c_stat) == "polling"


def test_map_cstat_authorized():
    assert map_cstat_to_status("100") == "authorized"
    assert map_cstat_to_status("150") == "authorized"
    assert map_cstat_to_status("110") == "denegada"


def test_sanitize_strips_secrets_and_xml():
    raw = sanitize_sefaz_raw(
        {
            "mode": "http",
            "password": "secret",
            "xml_nfe": "<NFe/>",
            "signed_xml": b"x",
            "body": "B" * 5000,
            "cStat": "100",
        }
    )
    assert "password" not in raw
    assert "xml_nfe" not in raw
    assert "signed_xml" not in raw
    assert raw["cStat"] == "100"
    assert len(raw["body"]) < 2000


def _minimal_snap():
    return {
        "emitente": {
            "cnpj": "37229907000137",
            "ie": "123",
            "name": "EXEQ",
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
                "quantity": "1",
                "unit_price_cents": 10000,
                "total_cents": 10000,
                "origin": "0",
                "csosn": "102",
                "taxes": {
                    "icms": {"regime": "sn", "csosn": "102", "value_cents": 0},
                    "pis": {"cst": "07", "value_cents": 0, "rate_bp": 0, "base_cents": 0},
                    "cofins": {"cst": "07", "value_cents": 0, "rate_bp": 0, "base_cents": 0},
                },
            }
        ],
        "totals": {
            "products_cents": 10000,
            "total_cents": 10000,
            "freight_cents": 0,
            "discount_cents": 0,
            "icms_cents": 0,
            "pis_cents": 0,
            "cofins_cents": 0,
        },
        "payment": {"method": "99", "amount_cents": 10000},
    }


def _passthrough_sign(nfe_xml, pfx_bytes, password=""):
    """Simula assinado (injeta Signature) para mocks de POST sem PFX real."""
    raw = nfe_xml if isinstance(nfe_xml, (bytes, bytearray)) else str(nfe_xml).encode()
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    if "Signature" in text:
        return raw if isinstance(raw, (bytes, bytearray)) else text.encode()
    # Namespace dsig mínimo — basta tag local Signature no preflight
    fake_sig = (
        '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">'
        "<SignedInfo/><SignatureValue>dGVzdA==</SignatureValue>"
        "</Signature>"
    )
    if "</NFe>" in text:
        text = text.replace("</NFe>", fake_sig + "</NFe>", 1)
    else:
        text = text + fake_sig
    return text.encode("utf-8")


def test_http_provider_cert_missing():
    r = HttpNfeProvider().emitir(
        invoice_snapshot=_minimal_snap(),
        context={},
    )
    assert r.status == "failed"
    assert r.rejection_code == "CERT"
    assert r.raw and "password" not in r.raw


@pytest.mark.django_db
def test_http_provider_mock_authorized(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = False
    authorized = SefazHttpResponse(
        http_status=200,
        body=_FIXTURE_AUTORIZADA,
        c_stat="100",
        x_motivo="Autorizado o uso da NF-e",
        protocol="135260000000001",
        access_key="35260837229907000137550010000000011000000010",
        lote_c_stat="104",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch("integrations.sefaz_nfe.sign.sign_nfe_xml", side_effect=_passthrough_sign),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_autorizacao",
            return_value=authorized,
        ),
    ):
        r = HttpNfeProvider().emitir(
            invoice_snapshot=_minimal_snap(),
            context={"tenant": tenant_a},
        )
    assert r.status == "authorized"
    assert r.protocol == "135260000000001"
    assert r.signed_xml is not None
    assert r.raw is not None
    assert r.raw.get("cStat") == "100"
    assert "xml_nfe" not in r.raw
    assert "password" not in r.raw


@pytest.mark.django_db
def test_http_provider_mock_rejected(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = False
    rejected = SefazHttpResponse(
        http_status=200,
        body=_FIXTURE_REJEITADA,
        c_stat="204",
        x_motivo="Rejeicao: Duplicidade de NF-e",
        protocol="",
        access_key="35260837229907000137550010000000011000000011",
        lote_c_stat="104",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch("integrations.sefaz_nfe.sign.sign_nfe_xml", side_effect=_passthrough_sign),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_autorizacao",
            return_value=rejected,
        ),
    ):
        r = HttpNfeProvider().emitir(
            invoice_snapshot=_minimal_snap(),
            context={"tenant": tenant_a},
        )
    assert r.status == "rejected"
    assert r.rejection_code == "204"


@pytest.mark.django_db
def test_http_dry_run_no_post(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = True
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch("integrations.sefaz_nfe.sign.sign_nfe_xml", side_effect=_passthrough_sign),
        patch("integrations.sefaz_nfe.transport.post_nfe_autorizacao") as post_mock,
    ):
        r = HttpNfeProvider().emitir(
            invoice_snapshot=_minimal_snap(),
            context={"tenant": tenant_a},
        )
    post_mock.assert_not_called()
    assert r.status == "failed"
    assert r.rejection_code == "DRY_RUN"
    assert r.signed_xml is not None


def test_post_autorizacao_uses_parse():
    class FakeResp:
        status_code = 200
        text = _FIXTURE_AUTORIZADA

    tmp = MagicMock()
    tmp.cleanup = MagicMock()
    with (
        patch(
            "integrations.sefaz_nfe.transport._pfx_to_pem_files",
            return_value=(Path("."), Path("."), tmp),
        ),
        patch("integrations.sefaz_nfe.transport.requests.post", return_value=FakeResp()),
    ):
        resp = post_nfe_autorizacao(
            url="https://example.test/ws",
            envi_nfe_xml=b"<enviNFe/>",
            pfx_bytes=b"x",
            password="",
        )
    assert resp.c_stat == "100"
    assert resp.lote_c_stat == "104"
    tmp.cleanup.assert_called_once()
