"""Download de documentos técnicos + polish wizard (Hub V4)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.fiscal.models import FiscalProfile
from apps.issuance.models import NfArtifact, NfIssue
from apps.master_data.models import Customer, Provider, ServiceCatalogItem, TaxRegime
from apps.ops.models import StoredFile
from shared.storage import get_storage


@pytest.fixture
def hub_ctx(db, settings, tmp_path):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    settings.STORAGE_BACKEND = "local"
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="hub-doc-qa", legal_name="Doc QA", document="11222333000181"
    )
    user = User.objects.create_user(
        email="docqa@exeq.local", password="Secret123!", name="Doc QA"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="Prest QA",
        tax_regime=TaxRegime.SIMPLES,
        is_active=True,
        address={"uf": "SP", "codigo_ibge": "3504107"},
    )
    customer = Customer.objects.create(
        tenant=tenant,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente QA",
        email="c@exeq.local",
        is_active=True,
        address={"telefone": "11999990000"},
    )
    service = ServiceCatalogItem.objects.create(
        tenant=tenant,
        service_code="1.01",
        description="Consultoria",
        lc116_item="1.01",
        is_active=True,
    )
    FiscalProfile.objects.create(
        tenant=tenant, name="SN", tax_regime=TaxRegime.SIMPLES
    )
    return {
        "tenant": tenant,
        "user": user,
        "provider": provider,
        "customer": customer,
        "service": service,
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


def _issue_with_pdf(ctx, settings, tmp_path):
    issue = NfIssue.objects.create(
        tenant=ctx["tenant"],
        idempotency_key="hub-doc-1",
        status=NfIssue.Status.AUTHORIZED,
        provider=ctx["provider"],
        customer=ctx["customer"],
        service=ctx["service"],
        ibge_code="3504107",
        competence_date="2026-08-01",
        amount_cents=10000,
        focus_ref="R-100",
    )
    storage = get_storage()
    key = f"nfse/{issue.id}/danfse.pdf"
    pdf = b"%PDF-1.4 hub-v4 test\n%%EOF\n"
    storage.put(key=key, data=pdf, content_type="application/pdf")
    stored = StoredFile.objects.create(
        tenant=ctx["tenant"],
        backend=StoredFile.Backend.LOCAL,
        object_key=key,
        content_type="application/pdf",
        size_bytes=len(pdf),
        checksum_sha256=StoredFile.checksum(pdf),
        purpose="nf_pdf",
    )
    NfArtifact.objects.create(
        tenant=ctx["tenant"],
        nf_issue=issue,
        kind=NfArtifact.Kind.PDF,
        stored_file=stored,
        checksum_sha256=stored.checksum_sha256,
    )
    return issue


@pytest.mark.django_db
def test_document_download_pdf(client, hub_ctx, settings, tmp_path):
    settings.LOCAL_STORAGE_ROOT = str(tmp_path)
    _login(client, hub_ctx)
    issue = _issue_with_pdf(hub_ctx, settings, tmp_path)
    url = reverse("hub-v4-nfse-doc-download", args=[issue.id, "pdf"])
    r = client.get(url)
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/pdf")
    assert b"%PDF" in b"".join(r.streaming_content)


@pytest.mark.django_db
def test_document_download_missing_404(client, hub_ctx):
    _login(client, hub_ctx)
    issue = NfIssue.objects.create(
        tenant=hub_ctx["tenant"],
        idempotency_key="hub-doc-missing",
        status=NfIssue.Status.AUTHORIZED,
        provider=hub_ctx["provider"],
        customer=hub_ctx["customer"],
        service=hub_ctx["service"],
        ibge_code="3504107",
        competence_date="2026-08-01",
        amount_cents=1000,
    )
    r = client.get(reverse("hub-v4-nfse-doc-download", args=[issue.id, "pdf"]))
    assert r.status_code == 404


@pytest.mark.django_db
def test_documents_page_and_wizard_structure(client, hub_ctx, settings, tmp_path):
    _login(client, hub_ctx)
    issue = _issue_with_pdf(hub_ctx, settings, tmp_path)
    r = client.get(reverse("hub-v4-nfse-documents", args=[issue.id]))
    assert r.status_code == 200
    body = r.content.decode()
    assert "Documentos Técnicos" in body
    assert "Baixar PDF" in body
    assert "Payload JSON" in body
    assert "Copiar JSON" in body

    wiz = client.get(reverse("hub-v4-nfse-wizard"))
    assert wiz.status_code == 200
    wh = wiz.content.decode()
    assert "1 · Tomador" in wh
    assert "2 · Serviço" in wh
    assert "3 · Tributação" in wh
    assert "4 · Revisão" in wh
    assert "Emitir NFS-e?" in wh
    assert "CPF/CNPJ" in wh
    assert "data-lookup-url" in wh
    assert "hub-customers-data" in wh
    assert "field-lc116" in wh
    assert "field-service-desc" in wh
    # Catálogo semeado (tenant vazio) ou existente na fixture
    assert "id_service_id" in wh
    assert "01.07" in wh or "Serviço" in wh


@pytest.mark.django_db
def test_lookup_existing_customer_json(client, hub_ctx):
    _login(client, hub_ctx)
    r = client.get(
        reverse("hub-v4-nfse-lookup"),
        {"document": hub_ctx["customer"].document},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["data"]["customer_id"] == str(hub_ctx["customer"].id)
    assert "Tomador encontrado" in data["data"]["message"]
