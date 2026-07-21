import json
from datetime import date

import httpx
import pytest

from integrations.payments.banks import BankPaymentGateway, C6PaymentGateway, InterPaymentGateway
from integrations.payments.errors import PaymentGatewayError
from integrations.payments.factory import get_payment_gateway


def test_inter_stub_register_cancel():
    gw = InterPaymentGateway(mode="stub", token="")
    result = gw.registrar_cobranca(
        amount_cents=2500,
        due_date=date(2024, 9, 1),
        description="Inter stub",
        customer_document="52998224725",
        customer_name="Pagador",
        external_reference="ext-1",
        idempotency_key="idem-inter-1",
    )
    assert result.external_ref.startswith("inter_")
    assert result.raw["mode"] == "stub"
    assert gw.cancelar(ref=result.external_ref).status == "cancelled"


def test_c6_stub_register():
    gw = C6PaymentGateway(mode="stub")
    result = gw.registrar_cobranca(
        amount_cents=100,
        due_date=date(2024, 9, 1),
        description="",
        customer_document="00000000000191",
        customer_name="X",
        external_reference="e",
        idempotency_key="k",
    )
    assert result.external_ref.startswith("c6_")


def test_inter_http_official_paths(monkeypatch, settings):
    settings.PAYMENT_HTTP_MODE = "http"
    settings.INTER_API_BASE_URL = "https://cdpj-sandbox.partners.uatinter.co"
    settings.INTER_CHARGE_PATH = "/cobranca/v3/cobrancas"
    settings.INTER_CANCEL_PATH_TMPL = "/cobranca/v3/cobrancas/{ref}/cancelar"
    settings.INTER_CANCEL_MOTIVO = "ACERTOS"
    settings.INTER_CONTA_CORRENTE = "123456789"

    seen = {"urls": [], "bodies": [], "headers": []}

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

        def request(self, method, url, headers=None, **kwargs):
            seen["urls"].append((method, url))
            seen["headers"].append(headers or {})
            if kwargs.get("json") is not None:
                seen["bodies"].append(kwargs["json"])
            if method == "POST" and url.endswith("/cobranca/v3/cobrancas"):
                return FakeResponse(200, {"codigoSolicitacao": "INT-99"})
            if method == "POST" and url.endswith("/cancelar"):
                return FakeResponse(202, {"status": "PROCESSANDO"})
            return FakeResponse(404, {"erro": "x"})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    gw = InterPaymentGateway(token="tok", mode="http")
    reg = gw.registrar_cobranca(
        amount_cents=1000,
        due_date=date(2024, 10, 1),
        description="HTTP",
        customer_document="52998224725",
        customer_name="Pagador",
        external_reference="ref-1",
        idempotency_key="idem-h",
        customer_address={
            "logradouro": "Rua B",
            "numero": "1",
            "bairro": "Centro",
            "cep": "12940001",
            "uf": "SP",
            "codigo_municipio": "3504107",
        },
    )
    assert reg.external_ref == "INT-99"
    assert seen["bodies"][0]["pagador"]["tipoPessoa"] == "FISICA"
    assert seen["bodies"][0]["pagador"]["cidade"] == "ATIBAIA"
    assert seen["bodies"][0]["pagador"]["cep"] == "12940001"
    assert seen["bodies"][0]["seuNumero"] == "ref-1"
    assert seen["bodies"][0]["mensagem"]["linha1"] == "HTTP"
    assert "linha5" in seen["bodies"][0]["mensagem"]
    assert seen["headers"][0]["x-conta-corrente"] == "123456789"
    assert gw.cancelar(ref="INT-99").status == "cancelled"
    assert seen["urls"][1] == (
        "POST",
        "https://cdpj-sandbox.partners.uatinter.co/cobranca/v3/cobrancas/INT-99/cancelar",
    )
    assert seen["bodies"][1] == {"motivoCancelamento": "ACERTOS"}


def test_c6_http_official_paths(monkeypatch, settings):
    settings.C6_API_BASE_URL = "https://baas-api-sandbox.c6bank.info"
    settings.C6_CHARGE_PATH = "/v1/bank_slips"
    settings.C6_CANCEL_PATH_TMPL = "/v1/bank_slips/{ref}/cancel"
    settings.C6_BILLING_SCHEME = "21"

    seen = {"urls": [], "bodies": []}

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

        def request(self, method, url, headers=None, **kwargs):
            seen["urls"].append((method, url))
            if kwargs.get("json") is not None:
                seen["bodies"].append(kwargs["json"])
            if method == "POST" and url.endswith("/v1/bank_slips"):
                return FakeResponse(200, {"id": "C6-77"})
            if method == "PUT" and url.endswith("/cancel"):
                return FakeResponse(200, {"status": "CANCELLED"})
            return FakeResponse(404, {"erro": "x"})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    gw = C6PaymentGateway(token="tok", mode="http")
    reg = gw.registrar_cobranca(
        amount_cents=15050,
        due_date=date(2024, 12, 31),
        description="Servico",
        customer_document="00.000.000/0001-91",
        customer_name="Empresa",
        external_reference="ORD-1001",
        idempotency_key="idem-c6",
    )
    assert reg.external_ref == "C6-77"
    body = seen["bodies"][0]
    assert body["amount"] == 150.5
    assert body["billing_scheme"] == "21"
    assert body["payer"]["tax_id"] == "00000000000191"
    assert "address" in body["payer"]
    assert gw.cancelar(ref="C6-77").status == "cancelled"
    assert seen["urls"][1] == (
        "PUT",
        "https://baas-api-sandbox.c6bank.info/v1/bank_slips/C6-77/cancel",
    )


def test_bank_http_requires_token(settings):
    settings.INTER_API_BASE_URL = "https://inter.test"
    gw = InterPaymentGateway(token="", mode="http")
    with pytest.raises(PaymentGatewayError, match="Token"):
        gw.registrar_cobranca(
            amount_cents=1,
            due_date=date(2024, 1, 1),
            description="",
            customer_document="1",
            customer_name="n",
            external_reference="r",
            idempotency_key="i",
        )


def test_bank_http_requires_base_url(settings):
    settings.INTER_API_BASE_URL = ""
    gw = InterPaymentGateway(token="tok", mode="http")
    with pytest.raises(PaymentGatewayError, match="Base URL"):
        gw.registrar_cobranca(
            amount_cents=1,
            due_date=date(2024, 1, 1),
            description="",
            customer_document="1",
            customer_name="n",
            external_reference="r",
            idempotency_key="i",
        )


def test_bank_http_error_status(monkeypatch, settings):
    settings.INTER_API_BASE_URL = "https://inter.test"

    class FakeResponse:
        status_code = 502
        text = "bad"

        def json(self):
            return {"erro": "down"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    gw = BankPaymentGateway(
        kind="inter",
        token="t",
        base_url="https://inter.test",
        mode="http",
    )
    with pytest.raises(PaymentGatewayError, match="502"):
        gw.registrar_cobranca(
            amount_cents=1,
            due_date=date(2024, 1, 1),
            description="",
            customer_document="1",
            customer_name="n",
            external_reference="r",
            idempotency_key="i",
        )


@pytest.mark.django_db
def test_factory_inter_env_token(tenant_a, settings):
    settings.INTER_API_TOKEN = "env-inter"
    tenant_a.settings = {"payment_provider": "inter"}
    tenant_a.save(update_fields=["settings"])
    gw = get_payment_gateway(tenant=tenant_a)
    assert isinstance(gw, InterPaymentGateway)
    assert gw.token == "env-inter"


@pytest.mark.django_db
def test_factory_c6_env_token(tenant_a, settings):
    settings.C6_API_TOKEN = "env-c6"
    tenant_a.settings = {"payment_provider": "c6"}
    tenant_a.save(update_fields=["settings"])
    gw = get_payment_gateway(tenant=tenant_a)
    assert isinstance(gw, C6PaymentGateway)
    assert gw.token == "env-c6"


@pytest.mark.django_db
def test_factory_asaas_env_token(tenant_a, settings):
    from integrations.payments.asaas import AsaasPaymentGateway

    settings.ASAAS_API_TOKEN = "env-asaas"
    tenant_a.settings = {"payment_provider": "asaas"}
    tenant_a.save(update_fields=["settings"])
    gw = get_payment_gateway(tenant=tenant_a)
    assert isinstance(gw, AsaasPaymentGateway)
    assert gw.token == "env-asaas"


def test_bank_http_missing_ref(monkeypatch, settings):
    settings.INTER_API_BASE_URL = "https://inter.test"

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    gw = InterPaymentGateway(token="tok", mode="http")
    with pytest.raises(PaymentGatewayError, match="sem id"):
        gw.registrar_cobranca(
            amount_cents=1,
            due_date=date(2024, 1, 1),
            description="",
            customer_document="1",
            customer_name="n",
            external_reference="r",
            idempotency_key="i",
        )


def test_bank_http_non_json_body(monkeypatch, settings):
    settings.C6_API_BASE_URL = "https://c6.test"

    class FakeResponse:
        status_code = 200
        text = "not-json"

        def json(self):
            raise ValueError("no json")

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    gw = C6PaymentGateway(token="tok", mode="http")
    with pytest.raises(PaymentGatewayError, match="sem id"):
        gw.registrar_cobranca(
            amount_cents=1,
            due_date=date(2024, 1, 1),
            description="",
            customer_document="1",
            customer_name="n",
            external_reference="r",
            idempotency_key="i",
        )


def test_default_paths_match_official(settings):
    assert settings.INTER_CHARGE_PATH == "/cobranca/v3/cobrancas"
    assert "{ref}" in settings.INTER_CANCEL_PATH_TMPL
    assert settings.C6_CHARGE_PATH == "/v1/bank_slips"


def test_inter_body_includes_multa_mora_and_agenda():
    gw = InterPaymentGateway(mode="stub", token="")
    body = gw._inter_charge_body(
        amount_cents=600,
        due_date=date(2026, 8, 1),
        description="Desc",
        customer_document="52998224725",
        customer_name="Pagador",
        external_reference="fallback",
        charge_options={
            "seu_numero": "CTRL01",
            "num_dias_agenda": 30,
            "multa_percent": 2.0,
            "mora_percent_am": 1.0,
            "message_lines": ["L1", "L2", "", "", ""],
        },
    )
    assert body["seuNumero"] == "CTRL01"
    assert body["numDiasAgenda"] == 30
    assert body["multa"] == {"codigo": "PERCENTUAL", "taxa": 2.0, "valor": 0}
    assert body["mora"] == {"codigo": "TAXAMENSAL", "taxa": 1.0, "valor": 0}
    assert body["mensagem"]["linha1"] == "L1"
    assert body["mensagem"]["linha2"] == "L2"


def test_inter_cancel_requires_valid_motivo():
    gw = InterPaymentGateway(mode="http", token="tok")
    with pytest.raises(PaymentGatewayError, match="motivoCancelamento"):
        gw._cancel_spec("REF", motivo_cancelamento="INVALIDO")


def test_inter_consultar_stub():
    gw = InterPaymentGateway(mode="stub", token="")
    result = gw.consultar_cobranca(ref="abc")
    assert result.external_ref == "abc"
    assert result.extras["situacao"] == "A_RECEBER"
