"""Rascunho NFS-e: domínio + wizard Hub V4."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue, save_nf_draft
from apps.master_data.models import Customer, Provider, ServiceCatalogItem, TaxRegime


@pytest.fixture
def draft_ctx(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="draft-hub-qa",
        legal_name="Draft Hub QA",
        document="11222333000181",
    )
    user = User.objects.create_user(
        email="draft.hub@exeq.local", password="Secret123!", name="Draft Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="Prest Draft",
        tax_regime=TaxRegime.SIMPLES,
        is_active=True,
        address={"uf": "SP", "codigo_ibge": "3504107"},
    )
    customer = Customer.objects.create(
        tenant=tenant,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Tomador Draft",
        is_active=True,
    )
    service = ServiceCatalogItem.objects.create(
        tenant=tenant,
        service_code="1.01",
        description="Consultoria",
        lc116_item="1.01",
        is_active=True,
        codigo_tributacao_nacional_iss="010101",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant, name="SN", tax_regime=TaxRegime.SIMPLES
    )
    catalog = create_catalog(tenant=tenant)
    add_rule(
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime=TaxRegime.SIMPLES,
        iss_rate=Decimal("0.0200"),
        simples_codigo_tributacao=3,
        valid_from=date(2024, 1, 1),
    )
    catalog.publish_checklist = {
        "csv_validated": True,
        "rules_reviewed": True,
        "terms_accepted": True,
    }
    catalog.save(update_fields=["publish_checklist"])
    publish_catalog(catalog)
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


@pytest.mark.django_db
def test_save_nf_draft_stays_draft(draft_ctx):
    issue = save_nf_draft(
        tenant=draft_ctx["tenant"],
        idempotency_key="draft-idem-1",
        provider=draft_ctx["provider"],
        customer=draft_ctx["customer"],
        service=draft_ctx["service"],
        fiscal_profile=draft_ctx["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 8, 1),
        amount_cents=15000,
    )
    assert issue.status == NfIssue.Status.DRAFT
    assert NfIssue.objects.filter(pk=issue.pk).count() == 1


@pytest.mark.django_db
def test_update_draft_and_create_submits(draft_ctx):
    issue = save_nf_draft(
        tenant=draft_ctx["tenant"],
        idempotency_key="draft-idem-2",
        provider=draft_ctx["provider"],
        customer=draft_ctx["customer"],
        service=draft_ctx["service"],
        fiscal_profile=draft_ctx["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 8, 1),
        amount_cents=10000,
    )
    updated = save_nf_draft(
        tenant=draft_ctx["tenant"],
        idempotency_key="draft-idem-2",
        provider=draft_ctx["provider"],
        customer=draft_ctx["customer"],
        service=draft_ctx["service"],
        fiscal_profile=draft_ctx["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 8, 15),
        amount_cents=25000,
        draft=issue,
    )
    assert updated.pk == issue.pk
    assert updated.amount_cents == 25000
    assert updated.status == NfIssue.Status.DRAFT

    emitted = create_nf_issue(
        tenant=draft_ctx["tenant"],
        idempotency_key="draft-idem-2",
        provider=draft_ctx["provider"],
        customer=draft_ctx["customer"],
        service=draft_ctx["service"],
        fiscal_profile=draft_ctx["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 8, 15),
        amount_cents=25000,
    )
    assert emitted.pk == issue.pk
    assert emitted.status != NfIssue.Status.DRAFT


@pytest.mark.django_db
def test_wizard_save_and_reload_draft(client, draft_ctx):
    _login(client, draft_ctx)
    r = client.post(
        reverse("hub-v4-nfse-wizard"),
        {
            "wizard_action": "save_draft",
            "confirm_emit": "0",
            "idempotency_key": "hub-draft-ui-1",
            "customer_id": str(draft_ctx["customer"].id),
            "service_id": str(draft_ctx["service"].id),
            "provider_id": str(draft_ctx["provider"].id),
            "fiscal_profile_id": str(draft_ctx["profile"].id),
            "competence_date": "2026-08-01",
            "amount": "199,90",
            "ibge_code": "3504107",
        },
    )
    assert r.status_code == 302
    issue = NfIssue.objects.get(tenant=draft_ctx["tenant"], idempotency_key="hub-draft-ui-1")
    assert issue.status == NfIssue.Status.DRAFT
    assert "draft=" in r.url

    reload = client.get(reverse("hub-v4-nfse-wizard"), {"draft": str(issue.id)})
    assert reload.status_code == 200
    html = reload.content.decode()
    assert "Rascunho" in html
    assert str(draft_ctx["customer"].id) in html
    assert "199,90" in html or "199.90" in html
