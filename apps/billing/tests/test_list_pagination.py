"""D8/D9 — paginação server-side + filtro status (charges / nf-issue)."""

from datetime import date, timedelta

import pytest

from apps.billing.due_date_rules import min_due_date
from apps.billing.models import Charge
from apps.billing.services import create_charge
from apps.fiscal.models import FiscalProfile
from apps.issuance.models import NfIssue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_customer, create_provider, create_service


def _due():
    return min_due_date() + timedelta(days=7)


@pytest.fixture
def customer(tenant_a):
    return create_customer(
        tenant=tenant_a,
        document="52998224725",
        document_type="cpf",
        name="Pagador",
    )


@pytest.fixture
def nf_setup(tenant_a):
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
    return {
        "provider": provider,
        "customer": customer,
        "service": service,
        "profile": profile,
    }


@pytest.mark.django_db
def test_charges_list_paginated(api_client, auth_header, tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    for i in range(3):
        create_charge(
            tenant=tenant_a,
            idempotency_key=f"page-chg-{i}",
            customer=customer,
            amount_cents=500,
            due_date=_due(),
        )
    res = api_client.get(
        "/api/v1/charges/?page_size=2&page=1",
        **auth_header,
    )
    assert res.status_code == 200
    assert "results" in res.data
    assert res.data["count"] == 3
    assert len(res.data["results"]) == 2
    assert res.data["next"]


@pytest.mark.django_db
def test_charges_filter_status(api_client, auth_header, tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    a = create_charge(
        tenant=tenant_a,
        idempotency_key="filt-reg",
        customer=customer,
        amount_cents=500,
        due_date=_due(),
    )
    b = create_charge(
        tenant=tenant_a,
        idempotency_key="filt-paid",
        customer=customer,
        amount_cents=500,
        due_date=_due(),
    )
    b.status = Charge.Status.PAID
    b.save(update_fields=["status"])

    res = api_client.get("/api/v1/charges/?status=paid", **auth_header)
    assert res.status_code == 200
    ids = {row["id"] for row in res.data["results"]}
    assert str(b.id) in ids
    assert str(a.id) not in ids


@pytest.mark.django_db
def test_charges_summary(api_client, auth_header, tenant_a, customer, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    create_charge(
        tenant=tenant_a,
        idempotency_key="sum-1",
        customer=customer,
        amount_cents=500,
        due_date=_due(),
    )
    res = api_client.get("/api/v1/charges/summary/", **auth_header)
    assert res.status_code == 200
    assert res.data["total"] >= 1
    assert res.data["by_status"].get("registered", 0) >= 1


@pytest.mark.django_db
def test_nf_issue_list_paginated_and_status_filter(
    api_client, auth_header, tenant_a, nf_setup
):
    for i, st in enumerate(
        [
            NfIssue.Status.AUTHORIZED,
            NfIssue.Status.AUTHORIZED,
            NfIssue.Status.QUEUED,
        ]
    ):
        NfIssue.objects.create(
            tenant=tenant_a,
            idempotency_key=f"nf-page-{i}",
            status=st,
            provider=nf_setup["provider"],
            customer=nf_setup["customer"],
            service=nf_setup["service"],
            fiscal_profile=nf_setup["profile"],
            ibge_code="3504107",
            competence_date=date(2026, 6, 15),
            amount_cents=1000,
        )

    page = api_client.get(
        "/api/v1/nf-issue/?page_size=2&page=1",
        **auth_header,
    )
    assert page.status_code == 200
    assert page.data["count"] == 3
    assert len(page.data["results"]) == 2

    filt = api_client.get(
        "/api/v1/nf-issue/?status=authorized",
        **auth_header,
    )
    assert filt.status_code == 200
    assert filt.data["count"] == 2
    assert all(r["status"] == "authorized" for r in filt.data["results"])

    proc = api_client.get(
        "/api/v1/nf-issue/?status=processing",
        **auth_header,
    )
    assert proc.status_code == 200
    assert proc.data["count"] == 1
    assert proc.data["results"][0]["status"] == "queued"

    summary = api_client.get("/api/v1/nf-issue/summary/", **auth_header)
    assert summary.status_code == 200
    assert summary.data["total"] == 3
