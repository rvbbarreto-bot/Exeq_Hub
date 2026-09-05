"""Testes T1–T10 — política de roteamento NFC-e ↔ NF-e."""

from __future__ import annotations

import pytest

from apps.fiscal.document_policy import DocumentModel, SaleContext, resolve_document_route


def _route(**kwargs):
    return resolve_document_route(SaleContext(**kwargs))


def test_t1_anonymous_sp_nfce_no_dest():
    route = _route(uf="SP", total_cents=10_000)
    assert route.ok
    assert route.model == DocumentModel.NFCE
    assert route.omit_dest is True


def test_t2_valid_cpf_nfce():
    route = _route(uf="SP", total_cents=10_000, cpf="529.982.247-25")
    assert route.ok
    assert route.model == DocumentModel.NFCE
    assert route.omit_dest is False


def test_t3_valid_cnpj_routes_nfe():
    route = _route(uf="SP", total_cents=10_000, cnpj="37.229.907/0001-37")
    assert route.ok
    assert route.model == DocumentModel.NFE


def test_t4_invalid_cpf_blocked():
    route = _route(uf="SP", total_cents=100, cpf="111.111.111-11")
    assert not route.ok
    assert route.model == DocumentModel.BLOCKED
    assert any(e["field"] == "cpf" for e in route.errors)


def test_t5_invalid_cnpj_blocked():
    route = _route(uf="SP", total_cents=100, cnpj="11.111.111/1111-11")
    assert not route.ok
    assert route.model == DocumentModel.BLOCKED


def test_t6_cpf_and_cnpj_blocked():
    route = _route(
        uf="SP",
        total_cents=100,
        cpf="529.982.247-25",
        cnpj="37.229.907/0001-37",
    )
    assert not route.ok
    assert route.model == DocumentModel.BLOCKED
    assert any("ambos" in e["message"] for e in route.errors)


def test_t7_anonymous_below_limit_ok():
    route = _route(uf="SP", total_cents=999_900)
    assert route.ok
    assert route.model == DocumentModel.NFCE


def test_t8_anonymous_at_limit_blocked():
    route = _route(uf="SP", total_cents=1_000_000)
    assert not route.ok
    assert route.model == DocumentModel.BLOCKED


def test_t8b_anonymous_delivery_blocked():
    route = _route(uf="SP", total_cents=100, delivery=True)
    assert not route.ok
    assert route.model == DocumentModel.BLOCKED


def test_t9_sp_uses_sp_policy():
    route = _route(uf="SP", total_cents=100)
    assert route.ok
    assert route.model == DocumentModel.NFCE


def test_t10_rj_uses_default_policy():
    route = _route(uf="RJ", total_cents=100)
    assert route.ok
    assert route.model == DocumentModel.NFCE
    assert route.omit_dest is True
