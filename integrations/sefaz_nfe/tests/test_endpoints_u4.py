"""U4 — catálogo multi-UF + matriz QA (sem rede SEFAZ)."""

from __future__ import annotations

import pytest

from integrations.sefaz_nfe.endpoints import (
    NFE_MULTI_UF_10,
    is_uf_supported,
    list_supported_ufs,
    qa_matrix_rows,
    resolve_endpoints,
)


def test_multi_uf_count_is_10():
    assert len(NFE_MULTI_UF_10) == 10
    assert len(set(NFE_MULTI_UF_10)) == 10
    assert NFE_MULTI_UF_10[0] == "SP"


@pytest.mark.parametrize("uf", list(NFE_MULTI_UF_10))
@pytest.mark.parametrize("tp_amb", ["1", "2"])
def test_resolve_all_ufs_https(uf, tp_amb):
    ep = resolve_endpoints(uf=uf, tp_amb=tp_amb)
    assert ep.uf == uf
    assert ep.tp_amb == tp_amb
    for url in (
        ep.autorizacao,
        ep.ret_autorizacao,
        ep.consulta_protocolo,
        ep.recepcao_evento,
        ep.status_servico,
    ):
        assert url.startswith("https://")
        assert " " not in url


def test_resolve_sp_homolog_unchanged():
    ep = resolve_endpoints(uf="SP", tp_amb="2")
    assert "homologacao.nfe.fazenda.sp.gov.br" in ep.autorizacao
    assert ep.authority == "SP"


def test_rj_sc_es_use_svrs():
    for uf in ("RJ", "SC", "ES"):
        ep = resolve_endpoints(uf=uf, tp_amb="2")
        assert ep.authority == "SVRS"
        assert "svrs.rs.gov.br" in ep.autorizacao


def test_unsupported_uf_raises():
    with pytest.raises(ValueError, match="fora do catálogo"):
        resolve_endpoints(uf="XX", tp_amb="2")


def test_list_and_flags():
    assert list_supported_ufs() == list(NFE_MULTI_UF_10)
    assert is_uf_supported("sp") is True
    assert is_uf_supported("XX") is False


def test_qa_matrix_20_rows():
    rows = qa_matrix_rows()
    assert len(rows) == 20  # 10 UF × 2 ambientes
    ufs = {r["uf"] for r in rows}
    assert ufs == set(NFE_MULTI_UF_10)
