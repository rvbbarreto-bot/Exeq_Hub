"""Homolog spike ALE — preflight e stub emit."""

from __future__ import annotations

import pytest

from apps.accounts.models import Tenant
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.homolog_spike import (
    ALE_CNPJ,
    build_homolog_preflight,
    run_homolog_spike,
)
from apps.nfe.models import NfeInvoice


@pytest.fixture
def ale_tenant(db, settings):
    settings.NFE_ENABLED = True
    tenant = Tenant.objects.create(
        slug="ALE",
        legal_name="ALE Piloto",
        document=ALE_CNPJ,
        settings={"nfe_enabled": True},
    )
    return tenant


@pytest.fixture
def ale_provider(ale_tenant):
    return Provider.objects.create(
        tenant=ale_tenant,
        document=ALE_CNPJ,
        legal_name="ALE Emitente",
        tax_regime=TaxRegime.SIMPLES,
        state_registration="1234567890",
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


@pytest.fixture
def ale_customer(ale_tenant):
    return Customer.objects.create(
        tenant=ale_tenant,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente ALE",
        address={
            "logradouro": "Av Cliente",
            "numero": "1",
            "uf": "SP",
            "codigo_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_preflight_stub_ok_without_cert(ale_tenant, ale_provider, settings):
    settings.NFE_ENABLED = True
    pf = build_homolog_preflight(tenant=ale_tenant, provider=ale_provider, http_mode="stub")
    assert pf["ok"] is True
    assert pf["ie_present"] is True


@pytest.mark.django_db
def test_preflight_http_blocks_without_cert(ale_tenant, ale_provider, settings):
    settings.NFE_ENABLED = True
    pf = build_homolog_preflight(tenant=ale_tenant, provider=ale_provider, http_mode="http")
    assert pf["ok"] is False
    assert "cert_missing" in pf["blockers"]


@pytest.mark.django_db
def test_run_homolog_spike_stub(ale_tenant, ale_provider, ale_customer, settings):
    settings.NFE_ENABLED = True
    inv, pf = run_homolog_spike(
        tenant=ale_tenant,
        provider=ale_provider,
        customer=ale_customer,
        mode="stub",
        valor_cents=2000,
    )
    assert pf["ok"] is True
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert inv.access_key


@pytest.mark.django_db
def test_preflight_http_fails_emit_without_rtc_seed(ale_tenant, ale_provider, settings):
    settings.NFE_ENABLED = True
    settings.NFE_RTC_MODE = "emit"
    pf = build_homolog_preflight(
        tenant=ale_tenant,
        provider=ale_provider,
        http_mode="http",
        rtc_mode="emit",
        issue_date=__import__("datetime").date(2026, 9, 6),
    )
    assert pf["ok"] is False
    assert pf["rtc_emit"]["ok"] is False


@pytest.mark.django_db
def test_write_spike_evidence(tmp_path, ale_tenant, ale_provider, ale_customer, settings):
    from apps.nfe.homolog_spike import write_spike_evidence

    settings.NFE_ENABLED = True
    inv, pf = run_homolog_spike(
        tenant=ale_tenant,
        provider=ale_provider,
        customer=ale_customer,
        mode="stub",
    )
    out = tmp_path / "evidence.json"
    ev = write_spike_evidence(
        inv=inv,
        provider=ale_provider,
        preflight=pf,
        mode="stub",
        dry_run=False,
        out=out,
        tenant_slug="ALE",
    )
    assert out.exists()
    assert ev["tenant"] == "ALE"
    assert ev["preflight"]["ok"] is True


@pytest.mark.django_db
def test_run_homolog_http_raises_on_preflight_fail(
    ale_tenant, ale_provider, ale_customer, settings
):
    settings.NFE_ENABLED = True
    with pytest.raises(__import__("apps.nfe.exceptions", fromlist=["NfeValidationError"]).NfeValidationError):
        run_homolog_spike(
            tenant=ale_tenant,
            provider=ale_provider,
            customer=ale_customer,
            mode="http",
            dry_run=False,
        )
