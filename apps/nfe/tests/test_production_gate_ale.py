"""Fase 2 / Trilha 1 — gate produção ALE (CNPJ 61536366000174)."""

from __future__ import annotations

import pytest

from apps.nfe.gate import build_gate_payload
from apps.nfe.homolog_spike import ALE_CNPJ, build_homolog_preflight
from apps.nfe.ie_validation import validate_emitter_ie


@pytest.fixture
def nfe_http_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "http"
    settings.NFE_DEFAULT_TP_AMB = "1"
    return settings


@pytest.fixture
def ale_tenant(db):
    from apps.accounts.models import Tenant

    return Tenant.objects.create(
        slug="ALE",
        legal_name="ALE Piloto",
        document=ALE_CNPJ,
        settings={"nfe_enabled": True},
    )


@pytest.fixture
def ale_provider(ale_tenant):
    from apps.master_data.models import Provider, TaxRegime

    return Provider.objects.create(
        tenant=ale_tenant,
        document=ALE_CNPJ,
        legal_name="ALE Emitente",
        tax_regime=TaxRegime.SIMPLES,
        state_registration="",
        address={
            "logradouro": "Rua Piloto",
            "numero": "100",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_gate_http_blocks_ale_without_ie(nfe_http_settings, ale_tenant, ale_provider):
    payload = build_gate_payload(tenant=ale_tenant, provider_id=str(ale_provider.id))
    ie_chk = next(c for c in payload["checks"] if c["id"] == "ie")
    assert ie_chk["ok"] is False
    assert payload["can_create"] is False


@pytest.mark.django_db
def test_gate_http_passes_ie_when_configured(nfe_http_settings, ale_tenant, ale_provider):
    ale_provider.state_registration = "123456789112"
    ale_provider.save(update_fields=["state_registration"])
    ok, label = validate_emitter_ie(ale_provider.state_registration, http_mode=True)
    assert ok is True
    payload = build_gate_payload(tenant=ale_tenant, provider_id=str(ale_provider.id))
    ie_chk = next(c for c in payload["checks"] if c["id"] == "ie")
    assert ie_chk["ok"] is True


@pytest.mark.django_db
def test_homolog_preflight_reports_ie_blocker(nfe_http_settings, ale_tenant, ale_provider):
    report = build_homolog_preflight(tenant=ale_tenant, provider=ale_provider, http_mode="http")
    assert report["ok"] is False
    assert "ie_missing" in report["blockers"]
