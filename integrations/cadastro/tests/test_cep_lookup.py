import pytest

from integrations.cadastro.cep_http import CepHttpGateway
from integrations.cadastro.cep_stub import STUB_CEP_MISSING, STUB_CEP_OK, CepStubGateway
from integrations.cadastro.exceptions import CadastroNotFoundError, CadastroProviderUnavailableError
from integrations.cadastro.factory import get_cep_gateway


def test_cep_factory_stub(settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    assert isinstance(get_cep_gateway(), CepStubGateway)


def test_cep_stub_ok():
    result = CepStubGateway().lookup_cep(cep=STUB_CEP_OK)
    assert result.municipio == "Atibaia"
    assert result.codigo_municipio_ibge == "3504107"


def test_cep_stub_missing():
    with pytest.raises(CadastroNotFoundError):
        CepStubGateway().lookup_cep(cep=STUB_CEP_MISSING)


def test_cep_http_maps_viacep(monkeypatch):
    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "cep": "12941-410",
                "logradouro": "Rua Almeida Garret",
                "bairro": "Centro",
                "localidade": "Atibaia",
                "uf": "SP",
                "ibge": "3504107",
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = CepHttpGateway().lookup_cep(cep="12941410")
    assert result.logradouro.startswith("Rua")
    assert result.uf == "SP"
    assert result.codigo_municipio_ibge == "3504107"


@pytest.mark.django_db
def test_lookup_cep_api(api_client, auth_header, settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    res = api_client.post(
        "/api/v1/master-data/lookup-cep",
        {"cep": STUB_CEP_OK},
        format="json",
        **auth_header,
    )
    assert res.status_code == 200, res.data
    assert res.data["municipio"] == "Atibaia"
    assert res.data["codigo_municipio_ibge"] == "3504107"


@pytest.mark.django_db
def test_lookup_cep_not_found_api(api_client, auth_header, settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    res = api_client.post(
        "/api/v1/master-data/lookup-cep",
        {"cep": STUB_CEP_MISSING},
        format="json",
        **auth_header,
    )
    assert res.status_code == 404
