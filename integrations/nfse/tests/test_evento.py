"""Testes do mapper pedRegEvento (cancelamento)."""

from lxml import etree

from integrations.nfse.evento import (
    EventoBuildError,
    build_cancel_ped_reg_evento_xml,
    build_ped_reg_id,
)
from integrations.nfse.tests.pfx_factory import make_test_pfx
from integrations.nfse.xmldsig import sign_ped_reg_evento_xml, verify_dps_has_signature
import pytest


CHAVE = "35041072237229907000137000000000006826077669419404"


def test_build_ped_reg_id():
    assert build_ped_reg_id(chave_acesso=CHAVE) == f"PRE{CHAVE}101101"


def test_build_cancel_xml_has_e101101():
    xml = build_cancel_ped_reg_evento_xml(
        chave_acesso=CHAVE,
        autor_cnpj="37229907000137",
        x_motivo="Cancelamento laboratorial EXEQ Hub apos emissao",
        tp_amb=1,
    )
    root = etree.fromstring(xml)
    assert root.tag.endswith("pedRegEvento")
    inf = root.find("{http://www.sped.fazenda.gov.br/nfse}infPedReg")
    assert inf is not None
    assert inf.get("Id") == f"PRE{CHAVE}101101"
    evt = inf.find("{http://www.sped.fazenda.gov.br/nfse}e101101")
    assert evt is not None
    assert evt.findtext("{http://www.sped.fazenda.gov.br/nfse}cMotivo") == "1"


def test_build_rejects_short_motivo():
    with pytest.raises(EventoBuildError):
        build_cancel_ped_reg_evento_xml(
            chave_acesso=CHAVE,
            autor_cnpj="37229907000137",
            x_motivo="curto",
        )


def test_sign_ped_reg_evento():
    pfx = make_test_pfx(password="segredo")
    unsigned = build_cancel_ped_reg_evento_xml(
        chave_acesso=CHAVE,
        autor_cnpj="37229907000137",
        x_motivo="Cancelamento laboratorial EXEQ Hub apos emissao",
    )
    signed = sign_ped_reg_evento_xml(
        evento_xml=unsigned, pfx_bytes=pfx, password="segredo"
    )
    assert verify_dps_has_signature(signed) is True
    root = etree.fromstring(signed)
    children = [etree.QName(c).localname for c in root]
    assert children[-1] == "Signature"
