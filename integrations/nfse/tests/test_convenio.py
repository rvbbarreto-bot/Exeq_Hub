"""Testes gate RF-01 / convênio municipal por ambiente."""

import pytest
from django.core.cache import cache
from django.test import override_settings

from integrations.nfse.convenio import (
    MunicipioNaoAderenteError,
    assert_municipio_aderente_nacional,
    get_convenio_status,
    normalize_sefin_environment,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_normalize_environment():
    assert normalize_sefin_environment("production") == "production"
    assert normalize_sefin_environment("prod") == "production"
    assert normalize_sefin_environment("homolog") == "homolog"


@override_settings(
    NFSE_CONVENIO_MODE="stub",
    NFSE_NATIONAL_IBGE_CODES="3504107",
    NFSE_CONVENIO_HOMOLOG_IBGE_CODES="",
    NFSE_CONVENIO_DENY_IBGE="",
)
def test_atibaia_apto_somente_producao_stub():
    """Estudo PO: Atibaia apta em produção; homolog restrita sem semente."""
    prod = get_convenio_status("3504107", environment="production")
    assert prod.aderente is True
    assert prod.environment == "production"

    homolog = get_convenio_status("3504107", environment="homolog")
    assert homolog.aderente is False
    assert homolog.environment == "homolog"
    with pytest.raises(MunicipioNaoAderenteError):
        assert_municipio_aderente_nacional("3504107", environment="homolog")


@override_settings(
    NFSE_CONVENIO_MODE="stub",
    NFSE_CONVENIO_HOMOLOG_IBGE_CODES="3504107",
    NFSE_CONVENIO_DENY_IBGE="",
)
def test_homolog_seed_lab_permite_atibaia():
    status = get_convenio_status("3504107", environment="homolog")
    assert status.aderente is True


@override_settings(NFSE_CONVENIO_MODE="stub", NFSE_NATIONAL_IBGE_CODES="3504107")
def test_unknown_ibge_nao_apto_em_producao():
    status = get_convenio_status("3550308", environment="production")
    assert status.aderente is False
    with pytest.raises(MunicipioNaoAderenteError):
        assert_municipio_aderente_nacional("3550308", environment="production")


@override_settings(NFSE_CONVENIO_DENY_IBGE="3504107")
def test_deny_list_force_block():
    with pytest.raises(MunicipioNaoAderenteError):
        assert_municipio_aderente_nacional("3504107", environment="production")


@override_settings(NFSE_CONVENIO_MODE="http", ADN_PARAM_BASE_URL="https://adn.test")
def test_convenio_http_200_apto(monkeypatch):
    from unittest.mock import MagicMock, patch

    import httpx

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"situacao": "apto", "codMun": "3504107"}

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        status = get_convenio_status("3504107", environment="production", force_refresh=True)
    assert status.aderente is True
    assert status.source == "http_cache"
    assert mock_client.get.called


@override_settings(NFSE_CONVENIO_MODE="http", ADN_PARAM_BASE_URL="https://adn.test")
def test_convenio_http_496_sem_mtls_nao_apto():
    from unittest.mock import MagicMock, patch

    mock_resp = MagicMock()
    mock_resp.status_code = 496
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.json.side_effect = Exception("not json")

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        status = get_convenio_status("3504107", environment="production", force_refresh=True)
    assert status.aderente is False
    assert status.source == "http_error"
    assert "496" in str(status.raw.get("error") or "")
