import pytest

from integrations.receita.exceptions import ReceitaCredentialsMissingError
from integrations.receita.factory import get_receita_gateway
from integrations.receita.http import ReceitaHttpGateway
from integrations.receita.stub import ReceitaStubGateway
from integrations.receita.stub_pdf import STUB_DAS_PDF


def test_factory_default_stub(settings):
    settings.RECEITA_HTTP_MODE = "stub"
    gw = get_receita_gateway()
    assert isinstance(gw, ReceitaStubGateway)
    assert gw.kind == "receita_stub"


def test_factory_http_mode(settings):
    settings.RECEITA_HTTP_MODE = "http"
    settings.SERPRO_CONSUMER_KEY = ""
    settings.SERPRO_CONSUMER_SECRET = ""
    gw = get_receita_gateway()
    assert isinstance(gw, ReceitaHttpGateway)
    with pytest.raises(ReceitaCredentialsMissingError):
        gw.capturar_das(cnpj="00000000000191", competencia="2024-06")


def test_stub_returns_pdf_bytes():
    result = ReceitaStubGateway().capturar_das(
        cnpj="00000000000191",
        competencia="2024-06",
    )
    assert result.pdf_bytes == STUB_DAS_PDF
    assert result.pdf_bytes.startswith(b"%PDF")
