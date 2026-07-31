"""Contrato estrutural mínimo DPS (SEC-P2-03 parcial)."""

import pytest

from integrations.nfse.dps import DpsBuildError, build_dps_xml_from_dict, to_sefin_dps_xml
from integrations.nfse.dps_contract import DpsContractError, assert_dps_structure
from integrations.nfse.tests.test_dps import _issue


def test_assert_dps_structure_accepts_hub_xml():
    xml = to_sefin_dps_xml(_issue(), tp_amb=2, serie=1, n_dps=7)
    assert_dps_structure(xml)


def test_assert_dps_structure_rejects_wrong_root():
    with pytest.raises(DpsContractError, match="Raiz"):
        assert_dps_structure(b"<NFSe/>")


def test_assert_dps_structure_rejects_missing_block():
    xml = to_sefin_dps_xml(_issue(), tp_amb=2, serie=1, n_dps=8)
    broken = xml.replace(b"<toma>", b"<xToma>").replace(b"</toma>", b"</xToma>")
    with pytest.raises(DpsContractError, match="toma"):
        assert_dps_structure(broken)


def test_build_rejects_incomplete_dict_via_contract():
    with pytest.raises(DpsBuildError, match="verAplic|toma|elementos"):
        build_dps_xml_from_dict(
            {
                "infDPS": {
                    "tpAmb": 2,
                    "dhEmi": "2026-07-29T12:00:00-03:00",
                    "serie": "1",
                    "nDPS": "1",
                    "dCompet": "2026-07-29",
                    "cLocEmi": "3504107",
                    "prest": {"CNPJ": "37229907000137"},
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
