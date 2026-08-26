"""Testes — texto livre por emissão (xDescServ / xInfComp)."""

from datetime import date
from unittest.mock import MagicMock

import pytest
from lxml import etree

from apps.master_data.models import Customer, TaxRegime
from integrations.nfse.dps import build_dps_xml_from_dict, to_sefin_dps_dict
from integrations.nfse.emission_text import (
    MAX_DESCRICAO_SERVICO,
    normalize_emission_fields,
    resolve_emission_text,
)
from integrations.nfse.mappers import to_focus_nfsen


def _issue(**overrides):
    provider = MagicMock()
    provider.document = "37229907000137"
    provider.tax_regime = TaxRegime.SIMPLES
    provider.municipal_registration = "12345"

    customer = MagicMock()
    customer.name = "TOMADOR TESTE"
    customer.document = "52998224725"
    customer.document_type = Customer.DocumentType.CPF
    customer.email = "toma@exeq.local"
    customer.address = {
        "logradouro": "Rua B",
        "numero": "1",
        "bairro": "Centro",
        "cep": "12940001",
        "codigo_municipio": "3504107",
    }

    service = MagicMock()
    service.description = "Servico de software"
    service.codigo_tributacao_nacional_iss = "010101"
    service.lc116_item = "1.01"
    service.service_code = "1.01"

    issue = MagicMock()
    issue.id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    issue.provider = provider
    issue.customer = customer
    issue.service = service
    issue.ibge_code = "3504107"
    issue.competence_date = date(2026, 7, 29)
    issue.amount_cents = 1500
    issue.resolved_params = {
        "iss_retained": False,
        "tributacao_iss": 1,
        "percentual_total_tributos_simples_nacional": 6.0,
    }
    issue.internal_payload = None
    for k, v in overrides.items():
        setattr(issue, k, v)
    return issue


def test_normalize_emission_fields_collapses_newlines():
    out = normalize_emission_fields(
        descricao_servico="Linha 1\nLinha 2",
        informacoes_complementares="Obs\nextra",
    )
    assert out["descricao_servico"] == "Linha 1 Linha 2"
    assert out["informacoes_complementares"] == "Obs extra"


def test_resolve_emission_text_prefers_draft_then_catalog():
    issue = _issue(
        internal_payload={
            "emission": {
                "descricao_servico": "Descricao na nota",
                "informacoes_complementares": "Contrato 123",
            }
        }
    )
    desc, comp = resolve_emission_text(issue)
    assert desc == "Descricao na nota"
    assert comp == "Contrato 123"


def test_resolve_emission_text_resolved_params_win():
    issue = _issue(
        resolved_params={
            "descricao_servico": "Via params",
            "informacoes_complementares": "Via comp",
        },
        internal_payload={"emission": {"descricao_servico": "Draft"}},
    )
    desc, comp = resolve_emission_text(issue)
    assert desc == "Via params"
    assert comp == "Via comp"


def test_to_sefin_dps_dict_includes_info_compl_xml():
    issue = _issue(
        internal_payload={
            "emission": {
                "descricao_servico": "Consultoria customizada",
                "informacoes_complementares": "Ref. OS 2026-08",
            }
        }
    )
    payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=7)
    serv = payload["infDPS"]["serv"]
    assert serv["cServ"]["xDescServ"] == "Consultoria customizada"
    assert serv["infoCompl"]["xInfComp"] == "Ref. OS 2026-08"

    xml = build_dps_xml_from_dict(payload)
    root = etree.fromstring(xml)
    ns = {"n": "http://www.sped.fazenda.gov.br/nfse"}
    assert root.xpath("//n:xDescServ/text()", namespaces=ns)[0] == "Consultoria customizada"
    assert root.xpath("//n:xInfComp/text()", namespaces=ns)[0] == "Ref. OS 2026-08"


def test_to_focus_nfsen_emission_fields():
    issue = _issue(
        internal_payload={
            "emission": {
                "descricao_servico": "Desc Focus",
                "informacoes_complementares": "Info livre",
            }
        }
    )
    body = to_focus_nfsen(issue)
    assert body["descricao_servico"] == "Desc Focus"
    assert body["informacoes_complementares"] == "Info livre"


def test_descricao_max_length():
    long_text = "x" * (MAX_DESCRICAO_SERVICO + 50)
    out = normalize_emission_fields(descricao_servico=long_text)
    assert len(out["descricao_servico"]) == MAX_DESCRICAO_SERVICO
