"""Testes cStat SEFIN → status consulta."""

from pathlib import Path

from integrations.nfse.sefin_status import (
    cstat_from_nfse_xml,
    resolve_status_from_nfse_payload,
    status_from_sefin_cstat,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_status_from_sefin_cstat_codes():
    assert status_from_sefin_cstat("100") == "authorized"
    assert status_from_sefin_cstat("101") == "cancelled"


def test_cstat_from_cancelada_fixture():
    xml = (_FIXTURES / "nfse_cancelada_minimal.xml").read_bytes()
    assert cstat_from_nfse_xml(xml) == "101"
    assert resolve_status_from_nfse_payload(xml_bytes=xml) == "cancelled"


def test_http_map_consult_cancelled_xml():
    from unittest.mock import MagicMock

    from integrations.nfse.sefin import SefinNfseProvider
    from integrations.nfse.sefin_client import SefinHttpResponse

    xml = (_FIXTURES / "nfse_cancelada_minimal.xml").read_bytes()
    chave = "35041071234567800019055001000000012312345678901234"
    fake = MagicMock()
    fake.consultar_nfse.return_value = SefinHttpResponse(
        status_code=200,
        data={"chaveAcesso": chave},
        xml_bytes=xml,
    )
    provider = SefinNfseProvider(mode="http", client=fake)
    result = provider.consultar(ref=chave)
    assert result.status == "cancelled"
    assert result.raw.get("status") == "cancelled"
