from apps.accounts.secrets import get_tenant_secret_plaintext
from django.conf import settings

from integrations.payments.asaas import AsaasPaymentGateway
from integrations.payments.banks import C6PaymentGateway, InterPaymentGateway
from integrations.payments.port import PaymentGateway
from integrations.payments.router import (
    PROVIDER_ASAAS,
    PROVIDER_C6,
    PROVIDER_INTER,
    resolve_payment_provider_kind,
)


def get_payment_gateway(
    *,
    tenant=None,
    tenant_settings: dict | None = None,
    provider_kind: str | None = None,
) -> PaymentGateway:
    kind = resolve_payment_provider_kind(
        tenant=tenant,
        tenant_settings=tenant_settings,
        provider_kind=provider_kind,
    )
    token = None
    if tenant is not None:
        token = get_tenant_secret_plaintext(
            tenant=tenant,
            provider=kind,
            key_name="api_token",
        )
    if not token and kind == PROVIDER_ASAAS:
        token = settings.ASAAS_API_TOKEN or ""
    if not token and kind == PROVIDER_INTER:
        token = getattr(settings, "INTER_API_TOKEN", "") or ""
    if not token and kind == PROVIDER_C6:
        token = getattr(settings, "C6_API_TOKEN", "") or ""

    if kind == PROVIDER_INTER:
        return InterPaymentGateway(token=token or None)
    if kind == PROVIDER_C6:
        return C6PaymentGateway(token=token or None)
    return AsaasPaymentGateway(token=token or None)
