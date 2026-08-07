"""U8 — filtros de lista T1 + timeline de eventos."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.listing import filter_invoice_queryset, sanitize_event_metadata
from apps.nfe.models import NfeInvoice, NfeInvoiceEvent
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items


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
        name="Cliente Busca Alpha",
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


def test_sanitize_strips_raw_body():
    out = sanitize_event_metadata(
        {
            "provider": "stub",
            "raw": {"cStat": "100", "xMotivo": "Autorizado", "huge": "x" * 500},
            "password": "secret",
        }
    )
    assert out["provider"] == "stub"
    assert out["cStat"] == "100"
    assert "huge" not in out
    assert "password" not in out
    assert "raw" not in out


@pytest.mark.django_db
def test_filter_q_and_status_and_default_period(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u8-list-1",
        issue_date=timezone.localdate(),
    )
    create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u8-list-old",
        issue_date=timezone.localdate() - timedelta(days=60),
    )
    qs = NfeInvoice.objects.filter(tenant=tenant_a)
    # default 30d hides old
    recent = filter_invoice_queryset(qs)
    assert recent.filter(id=inv.id).exists()
    assert recent.filter(idempotency_key="u8-list-old").count() == 0
    # search by customer name
    found = filter_invoice_queryset(qs, q="Alpha", days=0)
    assert found.filter(id=inv.id).exists()
    # status draft
    drafts = filter_invoice_queryset(qs, status="draft", days=0)
    assert drafts.count() >= 1
    # processing empty
    proc = filter_invoice_queryset(qs, status="processing", days=0)
    assert proc.count() == 0


@pytest.mark.django_db
def test_list_api_and_events_timeline(
    nfe_settings, tenant_a, provider_sp, customer_b2b, auth_header, api_client
):
    product = create_product(
        tenant=tenant_a,
        code="U8P",
        description="P",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u8-api-1",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    emit_invoice(inv)
    inv.refresh_from_db()

    list_url = reverse("nfe-invoices")
    r = api_client.get(
        list_url, {"q": "Alpha", "status": "authorized", "days": "30"}, **auth_header
    )
    assert r.status_code == 200
    ids = [row["id"] for row in r.data.get("results") or []]
    assert str(inv.id) in ids

    r_proc = api_client.get(list_url, {"status": "processing", "days": "0"}, **auth_header)
    assert r_proc.status_code == 200

    ev_url = reverse("nfe-invoice-events", kwargs={"pk": inv.id})
    er = api_client.get(ev_url, **auth_header)
    assert er.status_code == 200
    events = er.data["events"]
    assert len(events) >= 2  # draft + submitting / authorized
    assert events[0]["to_status"] == "draft"
    assert any(e["to_status"] == "authorized" for e in events)
    # raw stripped if present
    for e in events:
        assert "raw" not in (e.get("metadata") or {})


@pytest.mark.django_db
def test_events_isolated_per_tenant(
    nfe_settings, tenant_a, tenant_b, provider_sp, customer_b2b, auth_header, api_client
):
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u8-sec",
    )
    # forge event on invoice
    NfeInvoiceEvent.objects.create(
        tenant=tenant_a,
        invoice=inv,
        from_status="",
        to_status="draft",
        actor="x",
        metadata={"raw": {"cStat": "1"}},
    )
    url = reverse("nfe-invoice-events", kwargs={"pk": inv.id})
    # auth is tenant_a — ok
    r = api_client.get(url, **auth_header)
    assert r.status_code == 200
    assert r.data["events"]
