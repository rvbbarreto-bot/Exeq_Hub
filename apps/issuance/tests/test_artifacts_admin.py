from datetime import date
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.fiscal.models import FiscalProfile
from apps.fiscal.tax_engine import add_rule, create_catalog, publish_catalog
from apps.issuance.artifacts import ensure_authorized_artifacts
from apps.issuance.models import NfArtifact, NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service
from apps.ops.models import StoredFile


@pytest.fixture
def emission_setup(tenant_a):
    provider = create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="Prestador",
        tax_regime=TaxRegime.SIMPLES,
    )
    customer = create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Cliente",
    )
    service = create_service(
        tenant=tenant_a,
        service_code="1.01",
        description="Serviço",
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a,
        name="SN",
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
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


@pytest.mark.django_db
def test_ensure_artifacts_stub_creates_pdf_and_xml(tenant_a, emission_setup, settings, tmp_path):
    settings.FOCUS_HTTP_MODE = "stub"
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)

    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="art-stub-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=1000,
    )
    assert issue.status == NfIssue.Status.AUTHORIZED
    kinds = set(NfArtifact.objects.filter(nf_issue=issue).values_list("kind", flat=True))
    assert kinds == {NfArtifact.Kind.PDF, NfArtifact.Kind.XML}
    assert StoredFile.objects.filter(purpose="nf_xml").exists()


@pytest.mark.django_db
def test_ensure_artifacts_idempotent(tenant_a, emission_setup, settings, tmp_path):
    settings.FOCUS_HTTP_MODE = "stub"
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)

    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="art-idem-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=1000,
    )
    ensure_authorized_artifacts(issue)
    ensure_authorized_artifacts(issue)
    assert NfArtifact.objects.filter(nf_issue=issue).count() == 2


@pytest.mark.django_db
def test_artifact_admin_download(tenant_a, emission_setup, settings, tmp_path):
    settings.FOCUS_HTTP_MODE = "stub"
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)

    User.objects.create_superuser(
        email="po-art@exeq.local",
        password="Secret123!",
        name="PO",
    )
    client = Client()
    assert client.login(email="po-art@exeq.local", password="Secret123!")

    issue = create_nf_issue(
        tenant=tenant_a,
        idempotency_key="art-dl-1",
        provider=emission_setup["provider"],
        customer=emission_setup["customer"],
        service=emission_setup["service"],
        fiscal_profile=emission_setup["profile"],
        ibge_code="3504107",
        competence_date=date(2024, 6, 15),
        amount_cents=1000,
    )
    pdf = NfArtifact.objects.get(nf_issue=issue, kind=NfArtifact.Kind.PDF)
    url = reverse("admin:issuance_nfartifact_download", args=[pdf.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/pdf")
    content = b"".join(response.streaming_content)
    assert content.startswith(b"%PDF")
