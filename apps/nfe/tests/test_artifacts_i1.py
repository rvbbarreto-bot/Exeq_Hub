"""U3/I1 — artefatos XML NF-e: store idempotente + download."""

from __future__ import annotations

import pytest

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.artifacts import (
    ensure_authorized_xml,
    get_artifact,
    has_xml_authorized,
    read_artifact_bytes,
)
from apps.nfe.models import NfeArtifact, NfeInvoice
from apps.nfe.services import (
    allowed_actions,
    create_draft,
    create_product,
    emit_invoice,
    replace_items,
)


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        state_registration="",
        address={
            "logradouro": "Rua Jose Florido",
            "numero": "121",
            "bairro": "Jardim Alvinopolis",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente B2B",
        address={
            "logradouro": "Av Teste",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


def _emit_authorized(nfe_settings, tenant_a, provider_sp, customer_b2b, key="nfe-art-1"):
    product = create_product(
        tenant=tenant_a,
        code="SKU-ART",
        description="Item artefato",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key=key,
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    return emit_invoice(inv)


@pytest.mark.django_db
def test_emit_stores_xml_authorized(nfe_settings, tenant_a, provider_sp, customer_b2b):
    inv = _emit_authorized(nfe_settings, tenant_a, provider_sp, customer_b2b)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert has_xml_authorized(inv) is True
    art = get_artifact(inv, NfeArtifact.Kind.XML_AUTHORIZED)
    assert art is not None
    data = read_artifact_bytes(art)
    assert b"infNFe" in data or b"NFe" in data
    assert "download_xml" in allowed_actions(inv)
    assert "download_pdf" in allowed_actions(inv)


@pytest.mark.django_db
def test_store_artifact_idempotent(nfe_settings, tenant_a, provider_sp, customer_b2b):
    inv = _emit_authorized(nfe_settings, tenant_a, provider_sp, customer_b2b, key="idem-art")
    a1 = ensure_authorized_xml(inv)
    a2 = ensure_authorized_xml(inv)
    assert a1 is not None and a2 is not None
    assert a1.id == a2.id
    assert (
        NfeArtifact.objects.filter(
            invoice=inv, kind=NfeArtifact.Kind.XML_AUTHORIZED
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_download_xml_api(api_client, auth_header, nfe_settings, tenant_a, provider_sp, customer_b2b):
    inv = _emit_authorized(nfe_settings, tenant_a, provider_sp, customer_b2b, key="dl-xml")
    url = f"/api/v1/nfe/invoices/{inv.id}/artifacts/xml"
    r = api_client.get(url, **auth_header)
    assert r.status_code == 200, r.content
    assert "xml" in r["Content-Type"]
    assert b"NFe" in r.content or b"infNFe" in r.content
    assert r.get("X-Checksum-SHA256")


@pytest.mark.django_db
def test_download_xml_missing_returns_404(
    api_client, auth_header, nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="draft-no-xml",
    )
    r = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/artifacts/xml", **auth_header)
    assert r.status_code == 404


@pytest.mark.django_db
def test_download_xml_cross_tenant(
    api_client, auth_header, nfe_settings, tenant_a, tenant_b, provider_sp, customer_b2b
):
    inv = _emit_authorized(nfe_settings, tenant_a, provider_sp, customer_b2b, key="x-tenant")
    # auth_header is tenant_a; forge nothing else - just assert other tenant cannot list via filter
    # Create membership-less request isn't available; object scoped by tenant on get_object_or_404
    inv.tenant = tenant_b
    inv.save(update_fields=["tenant_id", "updated_at"])
    r = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/artifacts/xml", **auth_header)
    assert r.status_code == 404


@pytest.mark.django_db
def test_download_pdf_ok_after_emit(
    api_client, auth_header, nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _emit_authorized(nfe_settings, tenant_a, provider_sp, customer_b2b, key="pdf-ok")
    r = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/artifacts/pdf", **auth_header)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
