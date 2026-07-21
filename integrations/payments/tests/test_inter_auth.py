import json
import time
from datetime import date

import httpx
import pytest

from integrations.payments.banks import InterPaymentGateway
from integrations.payments.errors import PaymentGatewayError
from integrations.payments.factory import get_payment_gateway
from integrations.payments.inter_auth import (
    InterAuthClient,
    InterCredentials,
    InterToken,
    build_inter_auth_client,
    resolve_inter_credentials,
)


class _FakeMtls:
    ssl_context = object()

    def close(self):
        pass


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _creds(**overrides) -> InterCredentials:
    base = dict(
        client_id="cid",
        client_secret="csecret",
        cert_pem="-----BEGIN CERTIFICATE-----\nX\n-----END CERTIFICATE-----",
        key_pem="-----BEGIN PRIVATE KEY-----\nY\n-----END PRIVATE KEY-----",
        scope="boleto-cobranca.read boleto-cobranca.write",
        conta_corrente="123",
    )
    base.update(overrides)
    return InterCredentials(**base)


def test_credentials_complete_requires_oauth_and_cert():
    assert _creds().complete is True
    assert InterCredentials(client_id="a", client_secret="b").complete is False
    assert _creds(client_id="").complete is False


def test_oauth_token_cached(monkeypatch):
    posts = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, **kwargs):
            posts.append({"url": url, "data": kwargs.get("data")})
            return _FakeResponse(
                200,
                {
                    "access_token": "tok-abc",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                    "scope": "boleto-cobranca.write",
                },
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "integrations.payments.inter_auth.build_inter_mtls_context",
        lambda **k: _FakeMtls(),
    )

    auth = InterAuthClient(
        credentials=_creds(),
        base_url="https://cdpj-sandbox.partners.uatinter.co",
    )
    assert auth.get_access_token() == "tok-abc"
    assert auth.get_access_token() == "tok-abc"
    assert len(posts) == 1
    assert posts[0]["url"].endswith("/oauth/v2/token")
    assert posts[0]["data"]["grant_type"] == "client_credentials"
    assert "boleto-cobranca.write" in posts[0]["data"]["scope"]
    auth.close()


def test_oauth_force_refresh(monkeypatch):
    posts = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, **kwargs):
            posts.append(url)
            return _FakeResponse(
                200,
                {"access_token": f"tok-{len(posts)}", "expires_in": 3600},
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "integrations.payments.inter_auth.build_inter_mtls_context",
        lambda **k: _FakeMtls(),
    )
    auth = InterAuthClient(credentials=_creds(), base_url="https://inter.test")
    assert auth.get_access_token() == "tok-1"
    assert auth.get_access_token(force=True) == "tok-2"
    assert len(posts) == 2


def test_oauth_expired_token_refetches(monkeypatch):
    posts = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, **kwargs):
            posts.append(1)
            return _FakeResponse(
                200,
                {"access_token": f"n{len(posts)}", "expires_in": 3600},
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "integrations.payments.inter_auth.build_inter_mtls_context",
        lambda **k: _FakeMtls(),
    )
    auth = InterAuthClient(credentials=_creds(), base_url="https://inter.test")
    auth._token = InterToken(access_token="old", expires_at=time.time() - 10)
    assert auth.get_access_token() == "n1"
    assert len(posts) == 1


def test_oauth_http_error(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _FakeResponse(401, {"error": "invalid_client"})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "integrations.payments.inter_auth.build_inter_mtls_context",
        lambda **k: _FakeMtls(),
    )
    auth = InterAuthClient(credentials=_creds(), base_url="https://inter.test")
    with pytest.raises(PaymentGatewayError, match="OAuth Inter HTTP 401"):
        auth.get_access_token()


def test_request_json_uses_bearer_and_conta(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, *a, **k):
            seen["verify"] = k.get("verify")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _FakeResponse(200, {"access_token": "t1", "expires_in": 3600})

        def request(self, method, url, headers=None, **kwargs):
            seen["method"] = method
            seen["url"] = url
            seen["headers"] = headers
            return _FakeResponse(200, {"codigoSolicitacao": "UUID-1"})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "integrations.payments.inter_auth.build_inter_mtls_context",
        lambda **k: _FakeMtls(),
    )
    auth = InterAuthClient(credentials=_creds(), base_url="https://inter.test")
    data = auth.request_json("POST", "/cobranca/v3/cobrancas", json={"x": 1})
    assert data["codigoSolicitacao"] == "UUID-1"
    assert seen["headers"]["Authorization"] == "Bearer t1"
    assert seen["headers"]["x-conta-corrente"] == "123"
    assert seen["verify"] is _FakeMtls.ssl_context


def test_gateway_http_uses_auth_client(monkeypatch):
    class FakeAuth(InterAuthClient):
        def __init__(self):
            self.credentials = _creds()
            self.calls = []

        def request_json(self, method, path, *, headers=None, **kwargs):
            self.calls.append((method, path, headers))
            if path.endswith("/cobrancas"):
                return {"codigoSolicitacao": "AUTH-99"}
            return {"status": "PROCESSANDO"}

    auth = FakeAuth()
    gw = InterPaymentGateway(mode="http", auth=auth, token="")
    reg = gw.registrar_cobranca(
        amount_cents=100,
        due_date=date(2024, 10, 1),
        description="x",
        customer_document="52998224725",
        customer_name="P",
        external_reference="r1",
        idempotency_key="idem",
    )
    assert reg.external_ref == "AUTH-99"
    assert auth.calls[0][0] == "POST"
    assert auth.calls[0][1] == "/cobranca/v3/cobrancas"


def test_build_inter_auth_client_none_without_creds(settings):
    settings.INTER_CLIENT_ID = ""
    settings.INTER_CLIENT_SECRET = ""
    settings.INTER_CERT_PEM = ""
    settings.INTER_KEY_PEM = ""
    settings.INTER_CERT_PATH = ""
    settings.INTER_KEY_PATH = ""
    assert build_inter_auth_client() is None


def test_build_inter_auth_client_from_settings(settings):
    settings.INTER_CLIENT_ID = "id"
    settings.INTER_CLIENT_SECRET = "sec"
    settings.INTER_CERT_PEM = "CERT"
    settings.INTER_KEY_PEM = "KEY"
    settings.INTER_API_BASE_URL = "https://inter.test"
    client = build_inter_auth_client()
    assert isinstance(client, InterAuthClient)
    assert client.credentials.complete is True
    client.close()


@pytest.mark.django_db
def test_factory_prefers_oauth_auth(tenant_a, settings):
    settings.INTER_API_TOKEN = "legacy"
    settings.INTER_CLIENT_ID = "id"
    settings.INTER_CLIENT_SECRET = "sec"
    settings.INTER_CERT_PEM = "CERT"
    settings.INTER_KEY_PEM = "KEY"
    tenant_a.settings = {"payment_provider": "inter"}
    tenant_a.save(update_fields=["settings"])
    gw = get_payment_gateway(tenant=tenant_a)
    assert isinstance(gw, InterPaymentGateway)
    assert gw.auth is not None
    assert gw.token == "legacy"


@pytest.mark.django_db
def test_resolve_credentials_from_tenant_secret(tenant_a, settings):
    from apps.accounts.secrets import set_tenant_secret

    settings.INTER_CLIENT_ID = ""
    settings.INTER_CLIENT_SECRET = ""
    set_tenant_secret(
        tenant=tenant_a, provider="inter", key_name="client_id", plaintext="tid"
    )
    set_tenant_secret(
        tenant=tenant_a, provider="inter", key_name="client_secret", plaintext="tsec"
    )
    set_tenant_secret(
        tenant=tenant_a, provider="inter", key_name="cert_pem", plaintext="TCERT"
    )
    set_tenant_secret(
        tenant=tenant_a, provider="inter", key_name="key_pem", plaintext="TKEY"
    )
    creds = resolve_inter_credentials(tenant=tenant_a)
    assert creds.client_id == "tid"
    assert creds.complete is True
