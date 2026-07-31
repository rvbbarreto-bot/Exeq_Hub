from django.test import override_settings

from apps.master_data.models import TaxRegime
from integrations.nfse.betha import BethaNfseProvider
from integrations.nfse.factory import (
    get_nfse_provider,
    resolve_nfse_provider_kind,
    resolve_nfse_route,
)
from integrations.nfse.focus import FocusNfseProvider
from integrations.nfse.router import (
    ATIBAIA_IBGE,
    LAYOUT_BETHA,
    LAYOUT_NFSE,
    LAYOUT_NFSEN,
    LAYOUT_SEFIN,
)
from integrations.nfse.sefin import SefinNfseProvider


def test_atibaia_routes_to_sefin_by_default():
    route = resolve_nfse_route(ibge_code=ATIBAIA_IBGE, focus_layout="nfse")
    assert route.kind == "sefin"
    assert route.layout == LAYOUT_SEFIN
    provider = get_nfse_provider(ibge_code=ATIBAIA_IBGE)
    assert isinstance(provider, SefinNfseProvider)
    result = provider.emitir(payload={"issue_id": "11111111-1111-1111-1111-111111111111"})
    assert result.external_ref.startswith("SEFIN-")
    assert result.status == "authorized"
    assert "<NFSe" in result.raw["xml"]


@override_settings(NFSE_DEFAULT_PROVIDER="focus")
def test_lab_override_default_provider_focus_nfsen():
    route = resolve_nfse_route(ibge_code=ATIBAIA_IBGE, focus_layout="nfse")
    assert route.kind == "focus"
    assert route.layout == LAYOUT_NFSEN
    provider = get_nfse_provider(ibge_code=ATIBAIA_IBGE)
    assert isinstance(provider, FocusNfseProvider)
    assert provider.layout == LAYOUT_NFSEN


@override_settings(NFSE_BETHA_IBGE_CODES="3550308,4106902")
def test_betha_selected_by_ibge_allowlist_when_not_national():
    assert resolve_nfse_provider_kind(ibge_code="3550308") == "betha"
    route = resolve_nfse_route(ibge_code="3550308")
    assert route.layout == LAYOUT_BETHA
    assert isinstance(get_nfse_provider(ibge_code="3550308"), BethaNfseProvider)


def test_tenant_override_betha_wins_even_for_atibaia():
    route = resolve_nfse_route(
        ibge_code=ATIBAIA_IBGE,
        tenant_settings={"nfse_provider_by_ibge": {ATIBAIA_IBGE: "betha"}},
    )
    assert route.kind == "betha"
    assert route.layout == LAYOUT_BETHA


def test_tenant_override_focus_for_lab():
    route = resolve_nfse_route(
        ibge_code=ATIBAIA_IBGE,
        tenant_settings={"nfse_provider_by_ibge": {ATIBAIA_IBGE: "focus"}},
    )
    assert route.kind == "focus"
    assert route.layout == LAYOUT_NFSEN


@override_settings(NFSE_DEFAULT_PROVIDER="focus")
def test_default_municipal_nfse_when_layout_nfse_and_not_national():
    route = resolve_nfse_route(ibge_code="3550308", focus_layout="nfse")
    assert route.kind == "focus"
    assert route.layout == LAYOUT_NFSE
    provider = FocusNfseProvider(layout=LAYOUT_NFSE)
    result = provider.emitir(payload={"issue_id": "22222222-2222-2222-2222-222222222222"})
    assert result.external_ref.startswith("FOCUS-")
    assert result.raw["layout"] == LAYOUT_NFSE


@override_settings(NFSE_NATIONAL_MANDATORY_FROM="2026-09-01")
def test_simples_forces_national_sefin_from_mandatory_date():
    route = resolve_nfse_route(
        ibge_code="3550308",
        focus_layout="nfse",
        tax_regime=TaxRegime.SIMPLES,
        competence_date="2026-09-01",
    )
    assert route.kind == "sefin"
    assert route.layout == LAYOUT_SEFIN


@override_settings(NFSE_DEFAULT_PROVIDER="focus", NFSE_NATIONAL_MANDATORY_FROM="2026-09-01")
def test_simples_focus_lab_when_default_provider_focus():
    route = resolve_nfse_route(
        ibge_code="3550308",
        focus_layout="nfse",
        tax_regime=TaxRegime.SIMPLES,
        competence_date="2026-09-01",
    )
    assert route.kind == "focus"
    assert route.layout == LAYOUT_NFSEN


@override_settings(NFSE_NATIONAL_MANDATORY_FROM="2026-09-01")
def test_simples_before_cutoff_keeps_municipal():
    route = resolve_nfse_route(
        ibge_code="3550308",
        focus_layout="nfse",
        tax_regime=TaxRegime.SIMPLES,
        competence_date="2026-08-31",
    )
    assert route.layout == LAYOUT_NFSE


@override_settings(NFSE_NATIONAL_MANDATORY_FROM="2026-09-01", NFSE_BETHA_IBGE_CODES="3550308")
def test_simples_mandatory_overrides_betha():
    route = resolve_nfse_route(
        ibge_code="3550308",
        tax_regime=TaxRegime.SIMPLES,
        competence_date="2026-10-01",
    )
    assert route.kind == "sefin"
    assert route.layout == LAYOUT_SEFIN
