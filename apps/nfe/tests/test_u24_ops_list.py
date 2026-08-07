"""U24 — filtros pdf_pending/denegada + POST retry-pdf."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.artifacts import has_danfe_pdf
from apps.nfe.listing import filter_invoice_queryset
from apps.nfe.models import NfeInvoice
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
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        state_registration="",
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente",
        address={
            "logradouro": "Av T",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


def _emit_with_pdf_fail(tenant, provider, customer, key, monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("render fail")

    monkeypatch.setattr("integrations.sefaz_nfe.danfe.render.render_danfe_pdf", _boom)
    monkeypatch.setattr("integrations.sefaz_nfe.danfe.render_danfe_pdf", _boom)
    product = create_product(
        tenant=tenant,
        code=f"U24-{key[:6]}",
        description="P",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant,
        provider=provider,
        customer=customer,
        idempotency_key=f"u24-{key}",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv = emit_invoice(inv)
    inv.refresh_from_db()
    return inv


@pytest.mark.django_db
def test_filter_status_pdf_pending_and_denegada(
    nfe_settings, tenant_a, provider_sp, customer_b2b, monkeypatch
):
    inv = _emit_with_pdf_fail(tenant_a, provider_sp, customer_b2b, "pend", monkeypatch)
    assert (inv.last_validation or {}).get("pdf_pending") is True

    den = NfeInvoice.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        status=NfeInvoice.Status.REJECTED,
        series=1,
        number=88,
        number_consumed=True,
        tp_amb="2",
        total_cents=1,
        issue_date=timezone.localdate(),
        last_validation={"denegada": True},
        rejection_code="110",
    )

    qs = NfeInvoice.objects.filter(tenant=tenant_a)
    pdf_qs = filter_invoice_queryset(qs, status="pdf_pending", days=0)
    assert pdf_qs.filter(id=inv.id).exists()
    assert not pdf_qs.filter(id=den.id).exists()

    den_qs = filter_invoice_queryset(qs, status="denegada", days=0)
    assert den_qs.filter(id=den.id).exists()

    flag_qs = filter_invoice_queryset(qs, flag="pdf_pending", days=0)
    assert flag_qs.filter(id=inv.id).exists()


@pytest.mark.django_db
def test_retry_pdf_api_and_action(
    nfe_settings, tenant_a, provider_sp, customer_b2b, monkeypatch, api_client, auth_header
):
    inv = _emit_with_pdf_fail(tenant_a, provider_sp, customer_b2b, "retry", monkeypatch)
    assert "retry_pdf" in allowed_actions(inv)
    assert not has_danfe_pdf(inv)

    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render.render_danfe_pdf",
        lambda *_a, **_k: b"%PDF-1.4 u24\n%%EOF\n",
    )
    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render_danfe_pdf",
        lambda *_a, **_k: b"%PDF-1.4 u24\n%%EOF\n",
    )
    r = api_client.post(f"/api/v1/nfe/invoices/{inv.id}/retry-pdf", {}, **auth_header)
    assert r.status_code == 200
    assert r.data.get("pdf_retry_ok") is True
    inv.refresh_from_db()
    assert has_danfe_pdf(inv)
    assert not (inv.last_validation or {}).get("pdf_pending")
    assert "retry_pdf" not in allowed_actions(inv)


@pytest.mark.django_db
def test_list_status_pdf_pending_api(
    nfe_settings, tenant_a, provider_sp, customer_b2b, monkeypatch, api_client, auth_header
):
    inv = _emit_with_pdf_fail(tenant_a, provider_sp, customer_b2b, "list", monkeypatch)
    r = api_client.get("/api/v1/nfe/invoices/?status=pdf_pending&days=0", **auth_header)
    assert r.status_code == 200
    ids = [str(x["id"]) for x in r.data.get("results") or r.data]
    assert str(inv.id) in ids
