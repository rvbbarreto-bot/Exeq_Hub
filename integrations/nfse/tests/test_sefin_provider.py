"""Testes SefinNfseProvider — stub + HTTP mapeado."""

from unittest.mock import MagicMock

import pytest
from django.test import override_settings

from integrations.nfse.sefin import SefinHttpError, SefinNfseProvider
from integrations.nfse.sefin_client import SefinHttpResponse
from integrations.nfse.sefin_codec import xml_to_gzip_b64


def test_stub_emit_consultar_cancelar():
    provider = SefinNfseProvider(mode="stub")
    emitted = provider.emitir(payload={"issue_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"})
    assert emitted.status == "authorized"
    assert emitted.external_ref.startswith("SEFIN-")
    assert "<NFSe" in emitted.raw["xml"]

    consulted = provider.consultar(ref=emitted.external_ref)
    assert consulted.status == "authorized"

    cancelled = provider.cancelar(ref=emitted.external_ref, justificativa="x" * 20)
    assert cancelled.status == "cancelled"


@override_settings(SEFIN_HTTP_MODE="http")
def test_http_emit_requires_dps_xml():
    provider = SefinNfseProvider(mode="http", pfx_bytes=b"x", pfx_password="")
    with pytest.raises(SefinHttpError, match="dps_xml"):
        provider.emitir(payload={"issue_id": "1"})


def test_http_emit_authorized_via_injected_client():
    xml = b'<?xml version="1.0"?><NFSe><nNFSe>9</nNFSe></NFSe>'
    fake = MagicMock()
    fake.emitir_dps.return_value = SefinHttpResponse(
        status_code=201,
        data={"chaveAcesso": "CHAVE50DIGITS", "nfseXmlGZipB64": "<omitted>"},
        xml_bytes=xml,
    )
    provider = SefinNfseProvider(mode="http", client=fake)
    result = provider.emitir(payload={"dps_xml": b"<DPS/>"})
    assert result.status == "authorized"
    assert result.external_ref == "CHAVE50DIGITS"
    assert result.raw["xml"].startswith("<?xml")
    fake.close.assert_not_called()  # client injetado não é fechado pelo provider


def test_http_emit_rejected():
    fake = MagicMock()
    fake.emitir_dps.return_value = SefinHttpResponse(
        status_code=400,
        data={"erros": [{"codigo": "E001", "mensagem": "DPS invalida"}]},
        xml_bytes=None,
    )
    provider = SefinNfseProvider(mode="http", client=fake)
    result = provider.emitir(payload={"dps_xml": "<DPS/>"})
    assert result.status == "rejected"


def test_http_emit_from_gzip_b64_field():
    fake = MagicMock()
    fake.emitir_dps.return_value = SefinHttpResponse(
        status_code=200,
        data={"chaveAcesso": "K1"},
        xml_bytes=b"<NFSe/>",
    )
    provider = SefinNfseProvider(mode="http", client=fake)
    b64 = xml_to_gzip_b64(b"<DPS/>")
    result = provider.emitir(payload={"dps_xml_gzip_b64": b64})
    assert result.status == "authorized"
    fake.emitir_dps.assert_called_once()


def test_http_consultar():
    fake = MagicMock()
    fake.consultar_nfse.return_value = SefinHttpResponse(
        status_code=200,
        data={"chaveAcesso": "K2"},
        xml_bytes=b"<NFSe/>",
    )
    provider = SefinNfseProvider(mode="http", client=fake)
    result = provider.consultar(ref="K2")
    assert result.status == "authorized"


def test_http_cancel_requires_evento_xml():
    provider = SefinNfseProvider(mode="http", client=MagicMock())
    with pytest.raises(SefinHttpError, match="evento_xml"):
        provider.cancelar(ref="K", justificativa="motivo com quinze+")


def test_http_cancel_ok():
    fake = MagicMock()
    fake.registrar_evento.return_value = SefinHttpResponse(
        status_code=201, data={"ok": True}, xml_bytes=None
    )
    provider = SefinNfseProvider(mode="http", client=fake)
    result = provider.cancelar(
        ref="K",
        justificativa="motivo com quinze+",
        evento_xml=b"<pedRegEvento/>",
    )
    assert result.status == "cancelled"


def test_http_load_pfx_requires_tenant():
    provider = SefinNfseProvider(mode="http")
    with pytest.raises(SefinHttpError, match="tenant"):
        provider.emitir(payload={"dps_xml": b"<DPS/>"})


def test_http_processing_status():
    fake = MagicMock()
    fake.emitir_dps.return_value = SefinHttpResponse(
        status_code=202, data={}, xml_bytes=None
    )
    provider = SefinNfseProvider(mode="http", client=fake)
    result = provider.emitir(payload={"dps_xml": b"<DPS/>"})
    assert result.status == "processing"
