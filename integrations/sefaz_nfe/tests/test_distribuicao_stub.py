"""Stub NFeDistribuicaoDFe — cStat 137, 138, 656."""

from __future__ import annotations

import pytest

from integrations.sefaz_nfe.distribuicao import (
    CSTAT_CONSUMO_INDEVIDO,
    CSTAT_DOCUMENTOS_LOCALIZADOS,
    CSTAT_NENHUM_DOCUMENTO,
    StubNfeDistribuicaoProvider,
    get_nfe_distribuicao_provider,
    resolve_distribuicao_endpoints,
)


@pytest.fixture
def stub_provider():
    return StubNfeDistribuicaoProvider()


@pytest.mark.django_db
def test_get_provider_returns_stub_by_default(settings):
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    provider = get_nfe_distribuicao_provider()
    assert provider.kind == "stub"


def test_resolve_endpoints_homolog():
    ep = resolve_distribuicao_endpoints(tp_amb="2")
    assert "hom1.nfe.fazenda.gov.br" in ep.distribuicao


def test_resolve_endpoints_production():
    ep = resolve_distribuicao_endpoints(tp_amb="1")
    assert "www1.nfe.fazenda.gov.br" in ep.distribuicao


def test_stub_cstat_137(stub_provider, settings):
    settings.NFE_ENTRADA_STUB_MODE = "137"
    result = stub_provider.consultar_dist_nsu(cnpj="37229907000137", ult_nsu="0")
    assert result.c_stat == CSTAT_NENHUM_DOCUMENTO
    assert result.ult_nsu == "000000000000000"
    assert result.documents == ()


def test_stub_cstat_656(stub_provider, settings):
    settings.NFE_ENTRADA_STUB_MODE = "656"
    result = stub_provider.consultar_dist_nsu(cnpj="37229907000137", ult_nsu="0")
    assert result.c_stat == CSTAT_CONSUMO_INDEVIDO
    assert result.documents == ()


def test_stub_cstat_138_returns_documents(stub_provider, settings):
    settings.NFE_ENTRADA_STUB_MODE = "138"
    result = stub_provider.consultar_dist_nsu(cnpj="37229907000137", ult_nsu="0")
    assert result.c_stat == CSTAT_DOCUMENTOS_LOCALIZADOS
    assert len(result.documents) == 2
    assert result.documents[0].schema_type == "resNFe"
    assert b"resNFe" in result.documents[0].xml_bytes
    assert result.max_nsu == "000000000000002"


def test_stub_138_second_page(stub_provider, settings):
    settings.NFE_ENTRADA_STUB_MODE = "138"
    result = stub_provider.consultar_dist_nsu(cnpj="37229907000137", ult_nsu="1")
    assert result.c_stat == CSTAT_DOCUMENTOS_LOCALIZADOS
    assert len(result.documents) == 1
    assert result.documents[0].nsu == "000000000000002"


def test_stub_138_exhausted_returns_137(stub_provider, settings):
    settings.NFE_ENTRADA_STUB_MODE = "138"
    result = stub_provider.consultar_dist_nsu(cnpj="37229907000137", ult_nsu="2")
    assert result.c_stat == CSTAT_NENHUM_DOCUMENTO
