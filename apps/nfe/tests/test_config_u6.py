"""U6 — gate T0 honesto, config série, discard/clone."""

from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.gate import build_gate_payload, upsert_number_series
from apps.nfe.models import NfeInvoice, NfeNumberSeries
from apps.nfe.services import (
    allowed_actions,
    clone_invoice,
    create_draft,
    discard_draft,
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


@pytest.mark.django_db
def test_gate_can_create_stub_without_series_row(nfe_settings, tenant_a, provider_sp):
    payload = build_gate_payload(tenant=tenant_a)
    assert payload["enabled"] is True
    assert payload["can_create"] is True
    assert payload["next_number_estimated"] == 1
    series_chk = next(c for c in payload["checks"] if c["id"] == "series")
    assert series_chk["ok"] is True


@pytest.mark.django_db
def test_gate_http_requires_series(nfe_settings, tenant_a, provider_sp, settings):
    settings.NFE_HTTP_MODE = "http"
    provider_sp.state_registration = "123456789112"
    provider_sp.save(update_fields=["state_registration"])
    payload = build_gate_payload(tenant=tenant_a)
    series_chk = next(c for c in payload["checks"] if c["id"] == "series")
    assert series_chk["ok"] is False
    assert payload["can_create"] is False

    upsert_number_series(
        tenant=tenant_a,
        provider=provider_sp,
        series=1,
        tp_amb="2",
        next_number=40,
    )
    payload2 = build_gate_payload(tenant=tenant_a)
    assert payload2["next_number_estimated"] == 40
    assert next(c for c in payload2["checks"] if c["id"] == "series")["ok"] is True
    # cert still missing in http → can_create false
    assert payload2["can_create"] is False
    cert = next(c for c in payload2["checks"] if c["id"] == "cert")
    assert cert["ok"] is False


@pytest.mark.django_db
def test_config_put_series(nfe_settings, tenant_a, provider_sp, auth_header, api_client):
    url = reverse("nfe-config")
    resp = api_client.put(
        url,
        {
            "provider_id": str(provider_sp.id),
            "series": 1,
            "tp_amb": "2",
            "next_number": 15,
        },
        format="json",
        **auth_header,
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["series"]["next_number"] == 15
    assert NfeNumberSeries.objects.filter(
        tenant=tenant_a, provider=provider_sp, series=1, tp_amb="2"
    ).exists()

    get_resp = api_client.get(url, **auth_header)
    assert get_resp.status_code == 200
    assert get_resp.data["gate"]["can_create"] is True
    assert any(s["next_number"] == 15 for s in get_resp.data["series"])


@pytest.mark.django_db
def test_gate_api_can_create(nfe_settings, tenant_a, provider_sp, auth_header, api_client):
    url = reverse("nfe-gate")
    resp = api_client.get(url, **auth_header)
    assert resp.status_code == 200
    assert resp.data["can_create"] is True
    assert "supported_ufs" in resp.data


@pytest.mark.django_db
def test_discard_and_clone(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u6-discard",
    )
    assert "discard" in allowed_actions(inv)
    iid = inv.id
    discard_draft(inv, actor="test")
    assert not NfeInvoice.objects.filter(id=iid).exists()

    inv2 = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u6-clone-src",
    )
    replace_items(
        inv2,
        items=[
            {
                "code": "X",
                "description": "Item",
                "ncm": "21069090",
                "cfop": "5102",
                "quantity": "1",
                "unit_price_cents": 5000,
                "csosn": "102",
            }
        ],
    )
    inv2.status = NfeInvoice.Status.REJECTED
    inv2.number = 99
    inv2.number_consumed = True
    inv2.save(update_fields=["status", "number", "number_consumed", "updated_at"])
    assert "clone" in allowed_actions(inv2)
    clone = clone_invoice(
        inv2, idempotency_key=f"u6-clone-{uuid.uuid4().hex[:8]}", actor="test"
    )
    assert clone.id != inv2.id
    assert clone.status == NfeInvoice.Status.DRAFT
    assert clone.number is None
    assert clone.number_consumed is False
    assert clone.items.count() == 1


@pytest.mark.django_db
def test_upsert_blocks_regress_next_number(nfe_settings, tenant_a, provider_sp):
    upsert_number_series(
        tenant=tenant_a, provider=provider_sp, series=1, tp_amb="2", next_number=10
    )
    with pytest.raises(ValueError, match="menor"):
        upsert_number_series(
            tenant=tenant_a, provider=provider_sp, series=1, tp_amb="2", next_number=5
        )
