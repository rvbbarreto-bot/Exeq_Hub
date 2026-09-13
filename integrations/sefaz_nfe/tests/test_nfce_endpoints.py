"""Endpoints NFC-e mod 65 — pivot SP."""

from __future__ import annotations

from integrations.sefaz_nfe.nfce_endpoints import (
    as_nfe_endpoints,
    list_supported_nfce_ufs,
    resolve_nfce_endpoints,
)


def test_nfce_sp_homolog_urls():
    ep = resolve_nfce_endpoints(uf="SP", tp_amb="2")
    assert ep.uf == "SP"
    assert ep.tp_amb == "2"
    assert "homologacao.nfce.fazenda.sp.gov.br/ws" in ep.autorizacao
    assert ep.autorizacao.endswith("/NFeAutorizacao4.asmx")
    assert "homologacao.nfce.fazenda.sp.gov.br" in ep.qr_base_url


def test_nfce_sp_production_urls():
    ep = resolve_nfce_endpoints(uf="SP", tp_amb="1")
    assert "nfce.fazenda.sp.gov.br/ws" in ep.autorizacao
    assert "www.nfce.fazenda.sp.gov.br" in ep.qr_base_url


def test_nfce_as_nfe_endpoints_adapter():
    ep = resolve_nfce_endpoints(uf="SP", tp_amb="2")
    nfe = as_nfe_endpoints(ep)
    assert nfe.autorizacao == ep.autorizacao
    assert nfe.uf == "SP"


def test_nfce_catalog_lists_sp():
    assert list_supported_nfce_ufs() == ["SP"]
