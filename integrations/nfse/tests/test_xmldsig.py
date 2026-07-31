"""Testes XMLDSig DPS."""

import pytest
from lxml import etree

from integrations.nfse.dps import build_dps_xml_from_dict
from integrations.nfse.tests.pfx_factory import make_test_pfx
from integrations.nfse.xmldsig import (
    SefinXmlDSigError,
    sign_dps_xml,
    verify_dps_has_signature,
)


def _minimal_dps_xml() -> bytes:
    return build_dps_xml_from_dict(
        {
            "infDPS": {
                "tpAmb": 2,
                "dhEmi": "2026-07-29T12:00:00-03:00",
                "verAplic": "EXEQHUB_1.0",
                "serie": "1",
                "nDPS": "99",
                "dCompet": "2026-07-29",
                "tpEmit": 1,
                "cLocEmi": "3504107",
                "prest": {
                    "CNPJ": "37229907000137",
                    "regTrib": {"opSimpNac": 3, "regApTribSN": 1, "regEspTrib": 0},
                },
                "toma": {"CPF": "52998224725", "xNome": "TOMADOR"},
                "serv": {
                    "locPrest": {"cLocPrestacao": "3504107"},
                    "cServ": {"cTribNac": "010101", "xDescServ": "Servico teste"},
                },
                "valores": {
                    "vServPrest": {"vServ": "15.00"},
                    "trib": {
                        "tribMun": {"tribISSQN": 1, "tpRetISSQN": 1},
                        "totTrib": {"pTotTribSN": "6.00"},
                    },
                },
            }
        }
    )


def test_sign_dps_xml_embeds_signature_child_of_dps():
    pfx = make_test_pfx(password="segredo")
    unsigned = _minimal_dps_xml()
    assert verify_dps_has_signature(unsigned) is False
    signed = sign_dps_xml(dps_xml=unsigned, pfx_bytes=pfx, password="segredo")
    assert verify_dps_has_signature(signed) is True
    root = etree.fromstring(signed)
    assert root.tag.endswith("DPS")
    children = [etree.QName(c).localname for c in root]
    assert "infDPS" in children
    assert "Signature" in children
    assert children[-1] == "Signature"
    # Signature não deve ficar dentro de infDPS
    inf = root.find("{http://www.sped.fazenda.gov.br/nfse}infDPS")
    assert inf is not None
    assert not any(etree.QName(c).localname == "Signature" for c in inf)
    text = signed.decode("utf-8")
    assert "rsa-sha1" in text
    assert "SignatureValue" in text
    assert "X509Certificate" in text


def test_sign_rejects_missing_id():
    xml = b'<?xml version="1.0"?><DPS xmlns="http://www.sped.fazenda.gov.br/nfse"><infDPS/></DPS>'
    pfx = make_test_pfx(password="x")
    with pytest.raises(SefinXmlDSigError):
        sign_dps_xml(dps_xml=xml, pfx_bytes=pfx, password="x")


def test_sign_rejects_bad_pfx_password():
    unsigned = _minimal_dps_xml()
    pfx = make_test_pfx(password="certo")
    with pytest.raises(SefinXmlDSigError):
        sign_dps_xml(dps_xml=unsigned, pfx_bytes=pfx, password="errado")
