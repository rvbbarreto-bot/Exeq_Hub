from datetime import date

import pytest

from integrations.payments.asaas import AsaasPaymentGateway
from integrations.payments.banks import C6PaymentGateway, InterPaymentGateway
from integrations.payments.factory import get_payment_gateway
from integrations.payments.router import (
    PROVIDER_ASAAS,
    PROVIDER_C6,
    PROVIDER_INTER,
    resolve_payment_provider_kind,
)


def test_asaas_stub_register_and_cancel():
    gw = AsaasPaymentGateway(mode="stub", token="")
    result = gw.registrar_cobranca(
        amount_cents=1000,
        due_date=date(2024, 8, 1),
        description="Teste",
        customer_document="52998224725",
        customer_name="Pagador",
        external_reference="charge-1",
        idempotency_key="idem-1",
    )
    assert result.external_ref.startswith("asaas_")
    assert result.status == "registered"
    cancelled = gw.cancelar(ref=result.external_ref)
    assert cancelled.status == "cancelled"


def test_resolve_payment_provider_default():
    assert resolve_payment_provider_kind() == PROVIDER_INTER


def test_resolve_payment_provider_from_tenant_settings(tenant_a):
    tenant_a.settings = {"payment_provider": "asaas"}
    tenant_a.save(update_fields=["settings"])
    assert resolve_payment_provider_kind(tenant=tenant_a) == PROVIDER_ASAAS
    assert resolve_payment_provider_kind(provider_kind="c6") == PROVIDER_C6
    assert resolve_payment_provider_kind(provider_kind="unknown") == PROVIDER_INTER


@pytest.mark.django_db
def test_factory_selects_adapters(tenant_a):
    gw = get_payment_gateway(tenant=tenant_a)
    assert isinstance(gw, InterPaymentGateway)
    assert gw.kind == "inter"

    tenant_a.settings = {"payment_provider": "asaas"}
    tenant_a.save(update_fields=["settings"])
    gw_asaas = get_payment_gateway(tenant=tenant_a)
    assert isinstance(gw_asaas, AsaasPaymentGateway)
    assert gw_asaas.kind == "asaas"

    gw_c6 = get_payment_gateway(tenant=tenant_a, provider_kind="c6")
    assert isinstance(gw_c6, C6PaymentGateway)
    assert gw_c6.kind == "c6"
