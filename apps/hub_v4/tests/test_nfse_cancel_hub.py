"""Cancelamento de NFS-e autorizada no Hub V4."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles


@pytest.fixture
def hub_nfse_cancel_ctx(db):
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="hub-nfse-cancel",
        legal_name="Hub NFS-e Cancel",
        document="11222333000182",
    )
    user = User.objects.create_user(
        email="nfse.cancel@exeq.local", password="Secret123!", name="Cancel Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = create_provider(
        tenant=tenant,
        document="00000000000191",
        legal_name="Prestador Cancel Hub",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant,
        document="52998224725",
        document_type="cpf",
        name="Cliente Cancel",
    )
    service = create_service(
        tenant=tenant,
        service_code="1.01",
        description="Serviço teste",
        codigo_tributacao_nacional_iss="010101",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant,
        name="SN",
        tax_regime=TaxRegime.SIMPLES,
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
def test_hub_nfse_detail_shows_cancel_form_for_authorized(client, hub_nfse_cancel_ctx):
    ctx = hub_nfse_cancel_ctx
    issue = create_nf_issue(
        tenant=ctx["tenant"],
        idempotency_key="hub-cancel-ui",
        provider=ctx["provider"],
        customer=ctx["customer"],
        service=ctx["service"],
        fiscal_profile=ctx["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 2, 1),
        amount_cents=1000,
    )
    assert issue.status == NfIssue.Status.AUTHORIZED
    _login(client, ctx)
    detail = client.get(reverse("hub-v4-nfse-detail", args=[issue.id]))
    assert detail.status_code == 200
    html = detail.content.decode()
    assert "Cancelar NFS-e" in html
    assert "Motivo do cancelamento" in html
    assert "Erro na emissão" in html
    assert "Serviço não prestado" in html
    assert "Outros" in html
    assert 'maxlength="150"' in html


@pytest.mark.django_db
def test_hub_cancel_nfse_authorized(client, hub_nfse_cancel_ctx):
    ctx = hub_nfse_cancel_ctx
    issue = create_nf_issue(
        tenant=ctx["tenant"],
        idempotency_key="hub-cancel-post",
        provider=ctx["provider"],
        customer=ctx["customer"],
        service=ctx["service"],
        fiscal_profile=ctx["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 2, 1),
        amount_cents=1500,
    )
    _login(client, ctx)
    r = client.post(
        reverse("hub-v4-nfse-cancel", args=[issue.id]),
        {
            "motivo_cancelamento": "2",
            "justificativa": "Servico nao foi prestado conforme combinado com o cliente.",
        },
    )
    assert r.status_code == 302
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.CANCELLED

    detail = client.get(reverse("hub-v4-nfse-detail", args=[issue.id]))
    assert b"Cancelar NFS-e" not in detail.content


@pytest.mark.django_db
def test_hub_cancel_nfse_requires_motivo(client, hub_nfse_cancel_ctx):
    ctx = hub_nfse_cancel_ctx
    issue = create_nf_issue(
        tenant=ctx["tenant"],
        idempotency_key="hub-cancel-no-motivo",
        provider=ctx["provider"],
        customer=ctx["customer"],
        service=ctx["service"],
        fiscal_profile=ctx["profile"],
        ibge_code="3504107",
        competence_date=date(2026, 2, 1),
        amount_cents=1200,
    )
    _login(client, ctx)
    r = client.post(
        reverse("hub-v4-nfse-cancel", args=[issue.id]),
        {"justificativa": "Justificativa valida porem sem motivo selecionado."},
    )
    assert r.status_code == 302
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.AUTHORIZED
