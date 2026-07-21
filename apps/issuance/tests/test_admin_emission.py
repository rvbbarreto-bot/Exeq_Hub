from datetime import date
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.admin import NfIssueAdmin
from apps.issuance.models import NfIssue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service


@pytest.fixture
def emission_admin_setup(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador Admin",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente Admin",
    )
    service = create_service(
        tenant=tenant_a,
        service_code="1.01",
        description="Serviço Admin",
        codigo_tributacao_nacional_iss="010701",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a,
        name="SN-Admin",
        tax_regime=TaxRegime.SIMPLES,
    )
    catalog = create_catalog(tenant=tenant_a)
    add_rule(
        catalog=catalog,
        fiscal_profile=profile,
        ibge_code="3504107",
        municipio_nome="Atibaia",
        uf="SP",
        service_code="1.01",
        tax_regime=TaxRegime.SIMPLES,
        iss_rate=Decimal("0.0200"),
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
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


@pytest.mark.django_db
def test_admin_create_nf_issue_calls_engine(tenant_a, emission_admin_setup):
    User = get_user_model()
    user = User.objects.create_superuser(
        email="qa-admin@exeq.local",
        password="Secret123!",
        name="QA Admin",
    )
    site = AdminSite()
    model_admin = NfIssueAdmin(NfIssue, site)
    factory = RequestFactory()
    request = factory.post("/admin/issuance/nfissue/add/")
    request.user = user
    setattr(request, "session", {})
    from django.contrib.messages.storage.fallback import FallbackStorage

    setattr(request, "_messages", FallbackStorage(request))

    form = model_admin.get_form(request)(
        data={
            "tenant": str(tenant_a.id),
            "idempotency_key": "admin-qa-1",
            "provider": str(emission_admin_setup["provider"].id),
            "customer": str(emission_admin_setup["customer"].id),
            "service": str(emission_admin_setup["service"].id),
            "fiscal_profile": str(emission_admin_setup["profile"].id),
            "ibge_code": "3504107",
            "competence_date": "2024-06-15",
            "valor_reais": "10,00",
        }
    )
    assert form.is_valid(), form.errors
    obj = form.save(commit=False)
    model_admin.save_model(request, obj, form, change=False)
    issue = NfIssue.objects.get(idempotency_key="admin-qa-1")
    assert issue.status == NfIssue.Status.AUTHORIZED
    assert issue.focus_ref
    assert issue.amount_cents == 1000


@pytest.mark.django_db
def test_admin_cancel_detail_authorized(tenant_a, emission_admin_setup):
    from django.urls import reverse
    from django.test import Client

    from apps.issuance.services import create_nf_issue

    User = get_user_model()
    user = User.objects.create_superuser(
        email="qa-cancel@exeq.local",
        password="Secret123!",
        name="QA Cancel",
    )
    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="admin-cancel-1",
        provider=emission_admin_setup["provider"],
        customer=emission_admin_setup["customer"],
        service=emission_admin_setup["service"],
        fiscal_profile=emission_admin_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=1000,
    )
    assert issue.status == NfIssue.Status.AUTHORIZED

    client = Client()
    assert client.login(email="qa-cancel@exeq.local", password="Secret123!")
    url = reverse("admin:issuance_nfissue_cancel", args=[issue.pk])
    get_resp = client.get(url)
    assert get_resp.status_code == 200
    assert b"Confirmar cancelamento" in get_resp.content

    post_resp = client.post(url, {"confirm": "1"})
    assert post_resp.status_code == 302
    issue.refresh_from_db()
    assert issue.status == NfIssue.Status.CANCELLED
