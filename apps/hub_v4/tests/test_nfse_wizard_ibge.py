"""Wizard NFS-e — IBGE explícito (Sprint C)."""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse

SPRINT_C_TEST_SETTINGS = {
    "RTC_ENFORCE_NATIONAL_CATALOG": False,
    "NFSE_CONVENIO_HOMOLOG_IBGE_CODES": "3504107,3550308",
}

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.fiscal.models import FiscalProfile
from apps.fiscal.multimunicipio import resolve_wizard_ibge_code
from apps.fiscal.templates_factory import import_rules_csv
from apps.issuance.models import NfIssue
from apps.master_data.models import Customer, Provider, ServiceCatalogItem, TaxRegime


@pytest.fixture
def wizard_ibge_ctx(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="wizard-ibge-qa",
        legal_name="Wizard IBGE QA",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="wizard.ibge@exeq.local", password="Secret123!", name="Wizard IBGE"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="Prest Atibaia",
        tax_regime=TaxRegime.SIMPLES,
        is_active=True,
        address={"codigo_ibge": "3504107", "municipio": "Atibaia", "uf": "SP"},
    )
    customer = Customer.objects.create(
        tenant=tenant,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Tomador",
        is_active=True,
    )
    service = ServiceCatalogItem.objects.create(
        tenant=tenant,
        service_code="SVC-SUP-TI",
        description="Suporte",
        lc116_item="01.07",
        codigo_tributacao_nacional_iss="010701",
        is_active=True,
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant, name="SN", tax_regime=TaxRegime.SIMPLES, status="active"
    )
    csv_text = (
        "service_code,ibge_code,iss_rate,municipio_nome,uf\n"
        "01.07,3504107,0.02,Atibaia,SP\n"
        "01.07,3550308,0.05,São Paulo,SP\n"
    )
    import_rules_csv(tenant=tenant, profile=profile, csv_text=csv_text)
    return {
        "tenant": tenant,
        "user": user,
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


def _login(client, ctx):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": ctx["tenant"].slug,
            "email": ctx["user"].email,
            "password": "Secret123!",
        },
    )


def test_resolve_wizard_ibge_unit(wizard_ibge_ctx):
    assert (
        resolve_wizard_ibge_code(
            post_ibge="3550308", provider=wizard_ibge_ctx["provider"]
        )
        == "3550308"
    )


@pytest.mark.django_db
@override_settings(**SPRINT_C_TEST_SETTINGS)
def test_wizard_emit_sp_ibge(wizard_ibge_ctx, client):
    ctx = wizard_ibge_ctx
    _login(client, ctx)
    r = client.post(
        reverse("hub-v4-nfse-wizard"),
        {
            "wizard_action": "emit",
            "confirm_emit": "1",
            "idempotency_key": "wiz-sp-ibge",
            "customer_id": str(ctx["customer"].id),
            "service_id": str(ctx["service"].id),
            "provider_id": str(ctx["provider"].id),
            "fiscal_profile_id": str(ctx["profile"].id),
            "competence_date": "2026-08-01",
            "amount": "250,00",
            "ibge_code": "3550308",
            "service_description": "Suporte prestado em São Paulo",
        },
    )
    assert r.status_code == 302, r.content.decode()[:500]
    issue = NfIssue.objects.get(tenant=ctx["tenant"], idempotency_key="wiz-sp-ibge")
    assert issue.ibge_code == "3550308"
    assert issue.status != NfIssue.Status.REJECTED


@pytest.mark.django_db
def test_wizard_rejects_invalid_ibge(wizard_ibge_ctx, client):
    ctx = wizard_ibge_ctx
    _login(client, ctx)
    r = client.post(
        reverse("hub-v4-nfse-wizard"),
        {
            "wizard_action": "save_draft",
            "confirm_emit": "0",
            "idempotency_key": "wiz-bad-ibge",
            "customer_id": str(ctx["customer"].id),
            "service_id": str(ctx["service"].id),
            "provider_id": str(ctx["provider"].id),
            "fiscal_profile_id": str(ctx["profile"].id),
            "competence_date": "2026-08-01",
            "amount": "100,00",
            "ibge_code": "123",
            "service_description": "Teste",
        },
    )
    assert r.status_code == 200
    assert b"7 d" in r.content.lower() or b"ibge" in r.content.lower()
    assert not NfIssue.objects.filter(
        tenant=ctx["tenant"], idempotency_key="wiz-bad-ibge"
    ).exists()


@pytest.mark.django_db
def test_wizard_rejects_sp_without_rule(wizard_ibge_ctx, client):
    ctx = wizard_ibge_ctx
    _login(client, ctx)
    r = client.post(
        reverse("hub-v4-nfse-wizard"),
        {
            "wizard_action": "emit",
            "confirm_emit": "1",
            "idempotency_key": "wiz-no-rule",
            "customer_id": str(ctx["customer"].id),
            "service_id": str(ctx["service"].id),
            "provider_id": str(ctx["provider"].id),
            "fiscal_profile_id": str(ctx["profile"].id),
            "competence_date": "2026-08-01",
            "amount": "100,00",
            "ibge_code": "3304557",
            "service_description": "RJ sem regra",
        },
        follow=True,
    )
    assert b"Sem regra ISS" in r.content or b"regra ISS" in r.content
