import pytest

from integrations.cadastro.exceptions import CadastroNotFoundError, CadastroProviderUnavailableError
from integrations.cadastro.factory import get_cadastro_gateway
from integrations.cadastro.http import CadastroHttpGateway
from integrations.cadastro.mappers import map_brasilapi_cnpj
from integrations.cadastro.stub import STUB_CNPJ_MISSING, STUB_CNPJ_OK, CadastroStubGateway


def test_factory_defaults_to_stub(settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    gw = get_cadastro_gateway()
    assert isinstance(gw, CadastroStubGateway)


def test_factory_http_mode(settings):
    settings.CADASTRO_HTTP_MODE = "http"
    gw = get_cadastro_gateway()
    assert isinstance(gw, CadastroHttpGateway)


def test_stub_lookup_success():
    result = CadastroStubGateway().lookup_cnpj(cnpj=STUB_CNPJ_OK)
    assert result.legal_name
    assert result.address.uf == "SP"
    assert result.optante_simples is True


def test_stub_does_not_invent_data_for_real_cnpj():
    with pytest.raises(CadastroProviderUnavailableError) as exc:
        CadastroStubGateway().lookup_cnpj(cnpj="37229907000137")
    assert "CADASTRO_HTTP_MODE=http" in str(exc.value)


def test_stub_lookup_not_found():
    with pytest.raises(CadastroNotFoundError):
        CadastroStubGateway().lookup_cnpj(cnpj=STUB_CNPJ_MISSING)


def test_map_brasilapi_payload():
    payload = {
        "razao_social": "EMPRESA TESTE LTDA",
        "nome_fantasia": "Teste",
        "descricao_situacao_cadastral": "ATIVA",
        "data_inicio_atividade": "2010-01-15",
        "natureza_juridica": "206-2 - Sociedade Empresária Limitada",
        "cnae_fiscal": 6201501,
        "cnae_fiscal_descricao": "Desenvolvimento de programas",
        "cnaes_secundarios": [{"codigo": 6202300, "descricao": "Web"}],
        "descricao_porte": "DEMAIS",
        "opcao_pelo_simples": False,
        "opcao_pelo_mei": False,
        "ddd_telefone_1": "1133334444",
        "descricao_tipo_logradouro": "RUA",
        "logradouro": "Exemplo",
        "numero": "10",
        "bairro": "Centro",
        "cep": 12940000,
        "municipio": "Atibaia",
        "uf": "SP",
        "codigo_municipio_ibge": 3504107,
    }
    result = map_brasilapi_cnpj(payload, cnpj="19131243000197", provider_kind="test")
    assert result.legal_name == "EMPRESA TESTE LTDA"
    assert result.cnae_principal.startswith("6201501")
    assert result.address.logradouro.startswith("RUA")
    assert result.address.cep == "12940000"


def test_http_timeout(monkeypatch, settings):
    import httpx

    settings.CADASTRO_CNPJ_TIMEOUT = 0.01

    def boom(*_a, **_k):
        raise httpx.TimeoutException("timeout")

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return boom()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    gw = CadastroHttpGateway(provider="brasilapi")
    with pytest.raises(CadastroProviderUnavailableError) as exc:
        gw.lookup_cnpj(cnpj=STUB_CNPJ_OK)
    assert "timeout" in str(exc.value).lower() or "expirou" in str(exc.value).lower()


def test_http_not_found(monkeypatch):
    import httpx

    class FakeResp:
        status_code = 404

        def json(self):
            return {"message": "not found"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    with pytest.raises(CadastroNotFoundError):
        CadastroHttpGateway().lookup_cnpj(cnpj=STUB_CNPJ_OK)
