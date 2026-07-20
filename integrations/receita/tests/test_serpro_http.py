import base64
import json
from decimal import Decimal

import httpx
import pytest

from integrations.receita.exceptions import (
    ReceitaAuthError,
    ReceitaBusinessError,
    ReceitaCredentialsMissingError,
    ReceitaHttpNotConfiguredError,
)
from integrations.receita.factory import get_receita_gateway
from integrations.receita.http import ReceitaHttpGateway
from integrations.receita.serpro_payload import (
    build_gerar_das_envelope,
    competencia_to_periodo,
    map_gerar_das_response,
)
from integrations.receita.stub import ReceitaStubGateway


def test_factory_default_stub(settings):
    settings.RECEITA_HTTP_MODE = "stub"
    assert isinstance(get_receita_gateway(), ReceitaStubGateway)


def test_factory_http_without_creds_raises_on_call(settings):
    settings.RECEITA_HTTP_MODE = "http"
    settings.SERPRO_CONSUMER_KEY = ""
    settings.SERPRO_CONSUMER_SECRET = ""
    gw = get_receita_gateway(mode="http")
    assert isinstance(gw, ReceitaHttpGateway)
    with pytest.raises(ReceitaCredentialsMissingError):
        gw.capturar_das(cnpj="00000000000191", competencia="2024-06")


def test_competencia_to_periodo():
    assert competencia_to_periodo("2024-06") == "202406"


def test_build_envelope():
    body = build_gerar_das_envelope(
        cnpj="12.345.678/0001-90",
        competencia="2024-06",
        id_sistema="PGDASD",
        id_servico="GERARDAS12",
        versao_sistema="1.0",
    )
    assert body["contribuinte"]["numero"] == "12345678000190"
    assert body["pedidoDados"]["idServico"] == "GERARDAS12"
    dados = json.loads(body["pedidoDados"]["dados"])
    assert dados["periodoApuracao"] == "202406"


def test_map_gerar_das_response_ok():
    pdf = base64.b64encode(b"%PDF-1.4 stub").decode()
    payload = {
        "status": 200,
        "mensagens": [{"codigo": "00", "texto": "OK"}],
        "dados": json.dumps(
            [
                {
                    "pdf": pdf,
                    "cnpjCompleto": "00000000000191",
                    "detalhamento": {
                        "periodoApuracao": "202406",
                        "numeroDocumento": "123",
                        "dataVencimento": "20240720",
                        "valores": {
                            "principal": 150.75,
                            "multa": 0,
                            "juros": 1.25,
                            "total": 152.0,
                        },
                    },
                }
            ]
        ),
    }
    result = map_gerar_das_response(payload)
    assert result.valor_principal == Decimal("150.75")
    assert result.valor_juros == Decimal("1.25")
    assert result.data_vencimento == "2024-07-20"
    assert result.pdf_bytes.startswith(b"%PDF")
    assert result.compliance_status == "aprovado"


def test_map_gerar_das_rejects_http_status():
    with pytest.raises(ReceitaBusinessError):
        map_gerar_das_response(
            {
                "status": 422,
                "mensagens": [{"codigo": "E1", "texto": "sem declaração"}],
                "dados": "",
            }
        )


def test_capturar_das_http_flow(monkeypatch, settings):
    settings.RECEITA_HTTP_MODE = "http"
    pdf = base64.b64encode(b"%PDF-serpro").decode()
    auth_json = {
        "access_token": "tok-access",
        "jwt_token": "tok-jwt",
        "expires_in": 3600,
    }
    emit_json = {
        "status": 200,
        "mensagens": [],
        "dados": json.dumps(
            [
                {
                    "pdf": pdf,
                    "detalhamento": {
                        "dataVencimento": "20240720",
                        "valores": {"principal": 10, "multa": 0, "juros": 0, "total": 10},
                    },
                }
            ]
        ),
    }

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, data=None, json=None):
            calls["n"] += 1
            if "authenticate" in url:
                return FakeResponse(200, auth_json)
            return FakeResponse(200, emit_json)

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "integrations.receita.auth.build_mtls_context",
        lambda **kwargs: type(
            "M",
            (),
            {"ssl_context": object(), "close": lambda self: None},
        )(),
    )

    gw = ReceitaHttpGateway(
        consumer_key="key",
        consumer_secret="secret",
        pfx_bytes=b"fake-pfx",
        pfx_password="",
        contratante_cnpj="00000000000191",
    )
    result = gw.capturar_das(cnpj="00000000000191", competencia="2024-06")
    assert result.valor_principal == Decimal("10.00")
    assert result.pdf_bytes == b"%PDF-serpro"
    assert calls["n"] >= 2


def test_darf_without_service_id(settings):
    settings.SERPRO_ID_SERVICO_GERAR_DARF = ""
    gw = ReceitaHttpGateway(
        consumer_key="k",
        consumer_secret="s",
        pfx_bytes=b"x",
    )
    with pytest.raises(ReceitaHttpNotConfiguredError):
        gw.capturar_darf(cnpj="00000000000191", competencia="2024-06")


def test_competencia_invalid():
    with pytest.raises(ReceitaBusinessError):
        competencia_to_periodo("2024")


def test_periodo_to_iso_and_envelope_consolidacao():
    from integrations.receita.serpro_payload import periodo_to_iso_date

    assert periodo_to_iso_date(None) is None
    assert periodo_to_iso_date("202407") is None
    assert periodo_to_iso_date("2024-07-20") == "2024-07-20"
    body = build_gerar_das_envelope(
        cnpj="00000000000191",
        competencia="202406",
        id_sistema="PGDASD",
        id_servico="GERARDAS12",
        versao_sistema="1.0",
        data_consolidacao="2024-07-15",
    )
    dados = json.loads(body["pedidoDados"]["dados"])
    assert dados["dataConsolidacao"] == "20240715"


def test_map_gerar_das_nested_and_empty_edges():
    from integrations.receita.serpro_payload import map_gerar_das_response

    with pytest.raises(ReceitaBusinessError, match="sem dados"):
        map_gerar_das_response({"status": 200, "mensagens": ["x"], "dados": ""})

    with pytest.raises(ReceitaBusinessError, match="lista DAS vazia"):
        map_gerar_das_response({"status": 200, "dados": "[]"})

    with pytest.raises(ReceitaBusinessError, match="não reconhecido"):
        map_gerar_das_response({"status": 200, "dados": "1"})

    with pytest.raises(ReceitaBusinessError, match="Item DAS inválido"):
        map_gerar_das_response({"status": 200, "dados": json.dumps([1])})

    with pytest.raises(ReceitaBusinessError, match="base64"):
        map_gerar_das_response(
            {
                "status": 200,
                "dados": json.dumps([{"pdf": "ab", "valores": {}}]),
            }
        )

    nested = map_gerar_das_response(
        {
            "status": 200,
            "mensagens": ["ok-str"],
            "dados": {"listaDas": [{"valores": {"principal": None}, "linhaDigitavel": "x"}]},
        }
    )
    assert nested.valor_principal == Decimal("0.00")
    assert nested.linha_digitavel == "x"

    dict_item = map_gerar_das_response(
        {
            "status": 200,
            "mensagens": [{"codigo": "1"}],
            "dados": {"valores": {"principal": "2.5"}},
        }
    )
    assert dict_item.valor_principal == Decimal("2.50")

    with pytest.raises(ReceitaBusinessError):
        map_gerar_das_response(
            {"status": 500, "mensagens": ["plain"], "dados": ""}
        )


def test_http_missing_pfx():
    gw = ReceitaHttpGateway(consumer_key="k", consumer_secret="s", pfx_bytes=b"")
    with pytest.raises(ReceitaCredentialsMissingError, match="PFX"):
        gw.capturar_das(cnpj="00000000000191", competencia="2024-06")


def test_http_close_and_network_error(monkeypatch):
    gw = ReceitaHttpGateway(
        consumer_key="k",
        consumer_secret="s",
        pfx_bytes=b"pfx",
    )
    gw.close()

    class BoomAuth:
        def get_tokens(self, force=False):
            return type("T", (), {"access_token": "a", "jwt_token": "j"})()

        def _ensure_mtls(self):
            return type("M", (), {"ssl_context": object()})()

        def close(self):
            pass

    gw._auth = BoomAuth()

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "Client", FakeClient)
    from integrations.receita.exceptions import ReceitaHttpError

    with pytest.raises(ReceitaHttpError, match="rede"):
        gw.capturar_das(cnpj="00000000000191", competencia="2024-06")


def test_http_401_retry_and_bad_payload(monkeypatch, settings):
    settings.SERPRO_ID_SERVICO_GERAR_DARF = "GERARDARF"
    auth_json = {"access_token": "a", "jwt_token": "j", "expires_in": 60}
    emit_ok = {
        "status": 200,
        "mensagens": [],
        "dados": json.dumps(
            [{"detalhamento": {"valores": {"principal": 1, "multa": 0, "juros": 0}}}]
        ),
    }
    emit_calls = {"n": 0}

    class FakeResponse:
        def __init__(self, status_code, payload, text=None):
            self.status_code = status_code
            self._payload = payload
            self.text = text or json.dumps(payload)

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, data=None, json=None):
            if "authenticate" in url:
                return FakeResponse(200, auth_json)
            emit_calls["n"] += 1
            if emit_calls["n"] == 1:
                return FakeResponse(401, {"erro": "expired"})
            return FakeResponse(200, emit_ok)

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "integrations.receita.auth.build_mtls_context",
        lambda **kwargs: type("M", (), {"ssl_context": object(), "close": lambda self: None})(),
    )
    gw = ReceitaHttpGateway(
        consumer_key="key",
        consumer_secret="secret",
        pfx_bytes=b"fake-pfx",
        contratante_cnpj="00000000000191",
    )
    result = gw.capturar_darf(cnpj="00000000000191", competencia="2024-06")
    assert result.raw["tipo"] == "DARF"
    assert result.valor_principal == Decimal("1.00")
    assert emit_calls["n"] == 2

    class ErrClient(FakeClient):
        def post(self, url, headers=None, data=None, json=None):
            if "authenticate" in url:
                return FakeResponse(200, auth_json)
            return FakeResponse(500, {"erro": "x"}, text="boom")

    monkeypatch.setattr(httpx, "Client", ErrClient)
    from integrations.receita.exceptions import ReceitaHttpError

    with pytest.raises(ReceitaHttpError, match="500"):
        gw.capturar_das(cnpj="00000000000191", competencia="2024-06")

    class ListClient(FakeClient):
        def post(self, url, headers=None, data=None, json=None):
            if "authenticate" in url:
                return FakeResponse(200, auth_json)
            return FakeResponse(200, ["not", "dict"])

    monkeypatch.setattr(httpx, "Client", ListClient)
    with pytest.raises(ReceitaHttpError, match="inesperado"):
        gw.capturar_das(cnpj="00000000000191", competencia="2024-06")


def test_http_401_retry_network_error(monkeypatch):
    auth_json = {"access_token": "a", "jwt_token": "j", "expires_in": 60}
    calls = {"n": 0}

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, data=None, json=None):
            calls["n"] += 1
            if "authenticate" in url:
                return FakeResponse(200, auth_json)
            if calls["n"] == 2:
                return FakeResponse(401, {"e": 1})
            raise httpx.ConnectError("retry-down")

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "integrations.receita.auth.build_mtls_context",
        lambda **kwargs: type("M", (), {"ssl_context": object(), "close": lambda self: None})(),
    )
    gw = ReceitaHttpGateway(
        consumer_key="key",
        consumer_secret="secret",
        pfx_bytes=b"fake-pfx",
    )
    from integrations.receita.exceptions import ReceitaHttpError

    with pytest.raises(ReceitaHttpError, match="rede"):
        gw.capturar_das(cnpj="00000000000191", competencia="2024-06")
