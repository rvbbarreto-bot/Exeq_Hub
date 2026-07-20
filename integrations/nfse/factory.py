from apps.accounts.secrets import get_tenant_secret_plaintext
from integrations.nfse.betha import BethaNfseProvider
from integrations.nfse.focus import FocusNfseProvider
from integrations.nfse.port import NfseProvider
from integrations.nfse.router import EmissionRoute, resolve_emission_route


def resolve_nfse_provider_kind(
    *,
    ibge_code: str,
    tenant_settings: dict | None = None,
    focus_layout: str | None = None,
    tax_regime: str | None = None,
    competence_date=None,
) -> str:
    return resolve_emission_route(
        ibge_code=ibge_code,
        tenant_settings=tenant_settings,
        focus_layout=focus_layout,
        tax_regime=tax_regime,
        competence_date=competence_date,
    ).kind


def resolve_nfse_route(
    *,
    ibge_code: str,
    tenant_settings: dict | None = None,
    focus_layout: str | None = None,
    tenant=None,
    tax_regime: str | None = None,
    competence_date=None,
) -> EmissionRoute:
    if focus_layout is None and tenant is not None:
        focus_layout = getattr(tenant, "focus_layout", None)
    return resolve_emission_route(
        ibge_code=ibge_code,
        tenant_settings=tenant_settings,
        focus_layout=focus_layout,
        tax_regime=tax_regime,
        competence_date=competence_date,
    )


def get_nfse_provider(
    *,
    ibge_code: str,
    tenant_settings: dict | None = None,
    tenant=None,
    tax_regime: str | None = None,
    competence_date=None,
) -> NfseProvider:
    route = resolve_nfse_route(
        ibge_code=ibge_code,
        tenant_settings=tenant_settings,
        tenant=tenant,
        tax_regime=tax_regime,
        competence_date=competence_date,
    )
    if route.kind == "betha":
        return BethaNfseProvider()

    token = None
    if tenant is not None:
        token = get_tenant_secret_plaintext(
            tenant=tenant,
            provider="focus",
            key_name="api_token",
        )
    return FocusNfseProvider(token=token, layout=route.layout)
