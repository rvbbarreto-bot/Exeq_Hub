"""Testes cliente HTTP SEFIN (mTLS mockado)."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from integrations.nfse.sefin_client import (
    SEFIN_BASE_HOMOLOG,
    SEFIN_BASE_PROD,
    SefinHttpClient,
    SefinHttpError,
    resolve_sefin_base_url,
)
from integrations.nfse.sefin_codec import xml_to_gzip_b64
from integrations.nfse.tests.pfx_factory import make_test_pfx


@pytest.fixture
def pfx():
    return make_test_pfx(password="x")


def test_resolve_base_url_homolog(settings):
    settings.SEFIN_BASE_URL = ""
    assert resolve_sefin_base_url(environment="homolog") == SEFIN_BASE_HOMOLOG


def test_resolve_base_url_production(settings):
    settings.SEFIN_BASE_URL = ""
    assert resolve_sefin_base_url(environment="production") == SEFIN_BASE_PROD


def test_resolve_base_url_override(settings):
    settings.SEFIN_BASE_URL = "https://example.test/SefinNacional/"
    assert resolve_sefin_base_url(environment="homolog") == "https://example.test/SefinNacional"


def test_handshake_success(pfx):
    client = SefinHttpClient(pfx_bytes=pfx, pfx_password="x", base_url=SEFIN_BASE_HOMOLOG)
    mock_response = MagicMock()
    mock_response.status_code = 405

    with patch("integrations.nfse.sefin_client.httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.request.return_value = mock_response
        evidence = client.handshake()

    assert evidence["mtls"] is True
    assert evidence["http_status"] == 405
    assert "producaorestrita" in evidence["base_url"]
    client.close()


def test_handshake_transport_error(pfx):
    client = SefinHttpClient(pfx_bytes=pfx, pfx_password="x")
    with patch("integrations.nfse.sefin_client.httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.request.side_effect = httpx.ConnectError("boom")
        with pytest.raises(SefinHttpError, match="transporte"):
            client.handshake()
    client.close()


def test_emitir_dps_authorized(pfx):
    xml = b'<?xml version="1.0"?><NFSe><infNFSe><nNFSe>1</nNFSe></infNFSe></NFSe>'
    payload = {
        "chaveAcesso": "35041071234567800019055001000000012312345678901234",
        "nfseXmlGZipB64": xml_to_gzip_b64(xml),
        "tipoAmbiente": 2,
    }
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = payload
    mock_response.text = ""

    client = SefinHttpClient(pfx_bytes=pfx, pfx_password="x")
    with patch("integrations.nfse.sefin_client.httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.request.return_value = mock_response
        result = client.emitir_dps(dps_xml=b"<DPS/>")

    assert result.status_code == 201
    assert result.xml_bytes == xml
    assert "omitted" in str(result.data.get("nfseXmlGZipB64"))
    client.close()


def test_emitir_dps_server_error_raises(pfx):
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.json.return_value = {"mensagem": "indisponivel"}
    mock_response.text = "indisponivel"

    client = SefinHttpClient(pfx_bytes=pfx, pfx_password="x")
    with patch("integrations.nfse.sefin_client.httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.request.return_value = mock_response
        with pytest.raises(SefinHttpError) as exc:
            client.emitir_dps(dps_xml=b"<DPS/>")
    assert exc.value.status_code == 503
    client.close()


def test_consultar_and_evento(pfx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"chaveAcesso": "ABC"}
    mock_response.text = ""

    client = SefinHttpClient(pfx_bytes=pfx, pfx_password="x")
    with patch("integrations.nfse.sefin_client.httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.request.return_value = mock_response
        c1 = client.consultar_nfse(chave_acesso="ABC-123")
        c2 = client.consultar_dps(id_dps="DPS1")
        c3 = client.registrar_evento(chave_acesso="ABC", evento_xml=b"<evento/>")

    assert c1.status_code == 200
    assert c2.status_code == 200
    assert c3.status_code == 200
    client.close()


def test_safe_json_non_dict(pfx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = ["lista"]
    mock_response.text = "[]"

    client = SefinHttpClient(pfx_bytes=pfx, pfx_password="x")
    with patch("integrations.nfse.sefin_client.httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.request.return_value = mock_response
        result = client.consultar_nfse(chave_acesso="X")
    assert result.data["body"] == ["lista"]
    client.close()
