"""Testes mapper DPS Nacional."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from lxml import etree

from django.test import override_settings

from integrations.nfse.dps import (
    DpsBuildError,
    build_dps_id,
    build_dps_xml_from_dict,
    to_sefin_dps_dict,
    to_sefin_dps_xml,
)
from apps.master_data.models import Customer, TaxRegime


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
    for k, v in overrides.items():
        setattr(issue, k, v)
    return issue


def test_build_dps_id_format():
    dps_id = build_dps_id(
        c_loc_emi="3504107",
        prestador_doc="37229907000137",
        is_cpf=False,
        serie=1,
        n_dps=42,
    )
    assert dps_id.startswith("DPS35041072")
    assert len(dps_id) == 45
    assert dps_id.endswith("000000000000042")


def test_to_sefin_dps_dict_sn_me_epp():
    issue = _issue()
    payload = to_sefin_dps_dict(
        issue,
        tp_amb=2,
        serie=1,
        n_dps=10,
        dh_emi=datetime(2026, 7, 29, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )
    inf = payload["infDPS"]
    assert inf["tpAmb"] == 2
    assert inf["cLocEmi"] == "3504107"
    assert inf["prest"]["CNPJ"] == "37229907000137"
    assert inf["prest"]["regTrib"]["opSimpNac"] == 3
    assert inf["prest"]["regTrib"]["regApTribSN"] == 1
    assert "IM" not in inf["prest"]
    assert inf["valores"]["vServPrest"]["vServ"] == "15.00"
    assert inf["valores"]["trib"]["totTrib"]["pTotTribSN"] == "6.00"
    assert inf["serv"]["cServ"]["cTribNac"] == "010101"
    assert inf["toma"]["CPF"] == "52998224725"
    assert inf["Id"].startswith("DPS")


def test_build_xml_contains_namespace_and_blocks():
    issue = _issue()
    xml = to_sefin_dps_xml(issue, tp_amb=2, serie=1, n_dps=7)
    root = etree.fromstring(xml)
    assert root.tag.endswith("DPS")
    text = xml.decode("utf-8")
    assert "infDPS" in text
    assert "pTotTribSN" in text
    assert "pAliq" not in text
    assert "Signature" not in text
    assert 'Id="DPS' in text


def test_dps_paliq_when_iss_retained_sn():
    issue = _issue(
        resolved_params={
            "iss_retained": True,
            "iss_rate": "0.0500",
            "simples_codigo_tributacao": 3,
            "tributacao_iss": 1,
            "percentual_total_tributos_simples_nacional": 6.0,
        }
    )
    payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=11)
    trib_mun = payload["infDPS"]["valores"]["trib"]["tribMun"]
    assert trib_mun["tpRetISSQN"] == 2
    assert trib_mun["pAliq"] == "5.00"
    xml = to_sefin_dps_xml(issue, tp_amb=2, serie=1, n_dps=11)
    assert b"pAliq" in xml


def test_dps_paliq_non_simples_always():
    issue = _issue()
    issue.provider.tax_regime = TaxRegime.PRESUMIDO
    issue.resolved_params = {
        "iss_retained": False,
        "iss_rate": "0.0500",
        "simples_codigo_tributacao": 1,
        "tributacao_iss": 1,
        "c_trib_mun": "107",
        "codigo_tributacao_nacional_iss": "010701",
    }
    payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=12)
    assert payload["infDPS"]["prest"]["regTrib"]["opSimpNac"] == 1
    assert payload["infDPS"]["valores"]["trib"]["tribMun"]["pAliq"] == "5.00"
    assert payload["infDPS"]["serv"]["cServ"]["cTribMun"] == "107"


def test_dps_cnbs_from_service_and_override():
    issue = _issue()
    issue.service.codigo_nbs = "115013000"
    with override_settings(NFSE_DPS_CNBS_MODE="on"):
        payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=15)
    assert payload["infDPS"]["serv"]["cServ"]["cNBS"] == "115013000"
    with override_settings(NFSE_DPS_CNBS_MODE="on"):
        xml = to_sefin_dps_xml(issue, tp_amb=2, serie=1, n_dps=15)
    assert b"cNBS" in xml
    assert b"115013000" in xml


def test_dps_cnbs_override_in_draft_beats_service():
    issue = _issue()
    issue.service.codigo_nbs = "111111111"
    issue.internal_payload = {"emission": {"codigo_nbs": "115022000"}}
    with override_settings(NFSE_DPS_CNBS_MODE="on"):
        payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=16)
    assert payload["infDPS"]["serv"]["cServ"]["cNBS"] == "115022000"


def test_dps_cnbs_deferred_when_gate_off_even_with_code():
    issue = _issue()
    issue.service.codigo_nbs = "115013000"
    with override_settings(NFSE_DPS_CNBS_MODE="off"):
        payload = to_sefin_dps_dict(issue, tp_amb=1, serie=1, n_dps=18)
    assert "cNBS" not in payload["infDPS"]["serv"]["cServ"]
    with override_settings(NFSE_DPS_CNBS_MODE="off"):
        xml = to_sefin_dps_xml(issue, tp_amb=1, serie=1, n_dps=18)
    assert b"cNBS" not in xml


def test_dps_cnbs_homolog_gate_only_tp_amb_2():
    issue = _issue()
    issue.service.codigo_nbs = "115013000"
    with override_settings(NFSE_DPS_CNBS_MODE="homolog"):
        prod = to_sefin_dps_dict(issue, tp_amb=1, serie=1, n_dps=19)
        hom = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=20)
    assert "cNBS" not in prod["infDPS"]["serv"]["cServ"]
    assert hom["infDPS"]["serv"]["cServ"]["cNBS"] == "115013000"


def test_dps_omits_cnbs_when_absent():
    issue = _issue()
    issue.service.codigo_nbs = ""
    issue.service.nbs_item = None
    issue.internal_payload = None
    payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=17)
    assert "cNBS" not in payload["infDPS"]["serv"]["cServ"]
    xml = to_sefin_dps_xml(issue, tp_amb=2, serie=1, n_dps=17)
    assert b"cNBS" not in xml


def test_dps_c_trib_mun_from_params():
    issue = _issue(
        resolved_params={
            "iss_retained": False,
            "tributacao_iss": 1,
            "percentual_total_tributos_simples_nacional": 6.0,
            "c_trib_mun": "101",
            "codigo_tributacao_nacional_iss": "010101",
        }
    )
    payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=14)
    assert payload["infDPS"]["serv"]["cServ"]["cTribMun"] == "101"
    xml = to_sefin_dps_xml(issue, tp_amb=2, serie=1, n_dps=14)
    assert b"cTribMun" in xml


def test_dps_op_simp_from_resolved_params():
    issue = _issue(
        resolved_params={
            "iss_retained": False,
            "simples_codigo_tributacao": 2,
            "tributacao_iss": 1,
            "percentual_total_tributos_simples_nacional": 6.0,
        }
    )
    payload = to_sefin_dps_dict(issue, tp_amb=2, serie=1, n_dps=13)
    assert payload["infDPS"]["prest"]["regTrib"]["opSimpNac"] == 2


def test_rejects_short_ctribnac():
    issue = _issue()
    issue.service.codigo_tributacao_nacional_iss = "1"
    issue.service.lc116_item = ""
    issue.service.service_code = "1"
    with pytest.raises(DpsBuildError):
        to_sefin_dps_dict(issue)


def test_build_dps_xml_from_dict_requires_prestador():
    with pytest.raises(DpsBuildError):
        build_dps_xml_from_dict(
            {
                "infDPS": {
                    "tpAmb": 2,
                    "dhEmi": "2026-07-29T12:00:00-03:00",
                    "serie": "1",
                    "nDPS": "1",
                    "dCompet": "2026-07-29",
                    "cLocEmi": "3504107",
                    "prest": {},
                    "serv": {
                        "locPrest": {"cLocPrestacao": "3504107"},
                        "cServ": {"cTribNac": "010101", "xDescServ": "x"},
                    },
                    "valores": {
                        "vServPrest": {"vServ": "10.00"},
                        "trib": {"tribMun": {"tribISSQN": 1, "tpRetISSQN": 1}},
                    },
                }
            }
        )
