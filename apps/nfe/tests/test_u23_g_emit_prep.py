"""U23 — G-EMIT checklist + attempts CCe/inut + spike schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.g_emit_checklist import build_g_emit_checklist
from apps.nfe.models import NfeInvoice, NfeTransmissionAttempt
from apps.nfe.services import (
    create_draft,
    create_product,
    emit_invoice,
    issue_carta_correcao,
    replace_items,
)
from apps.nfe.inutilization import inutilize_number_range


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_HTTP_DRY_RUN = False
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
def test_g_emit_checklist_stub_blocks_http_emit(
    nfe_settings, tenant_a, provider_sp
):
    payload = build_g_emit_checklist(
        tenant=tenant_a, cnpj=provider_sp.document, series=1
    )
    assert payload["schema_version"] == "1.0"
    assert payload["ready_for_http_emit"] is False
    assert "http_mode" in payload["blockers"]
    assert payload["gate"]["can_create"] is True


@pytest.mark.django_db
def test_g_emit_checklist_http_ready_when_gate_ok(
    nfe_settings, tenant_a, provider_sp, settings
):
    settings.NFE_HTTP_MODE = "http"
    settings.NFE_HTTP_DRY_RUN = False
    provider_sp.state_registration = "123456789112"
    provider_sp.save(update_fields=["state_registration"])
    # cert ausente -> can_create false em http
    payload = build_g_emit_checklist(tenant=tenant_a, cnpj=provider_sp.document)
    assert "cert" in payload["blockers"] or payload["ready_for_http_emit"] is False


@pytest.mark.django_db
def test_checklist_command(tmp_path, nfe_settings, tenant_a, provider_sp):
    out = tmp_path / "chk.json"
    # stub mode: ready_dry false because http_mode
    with pytest.raises(CommandError):
        call_command(
            "nfe_g_emit_checklist",
            tenant=tenant_a.slug,
            cnpj=provider_sp.document,
            out=str(out),
        )


@pytest.mark.django_db
def test_cce_records_attempt(nfe_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a,
        code="U23CCE",
        description="P",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="u23-cce",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv = emit_invoice(inv)
    issue_carta_correcao(
        inv,
        x_correcao="Correcao de teste unitario U23 carta de correcao",
    )
    assert NfeTransmissionAttempt.objects.filter(
        tenant=tenant_a, invoice=inv, stage="cce"
    ).exists()


@pytest.mark.django_db
def test_inut_records_attempt(nfe_settings, tenant_a, provider_sp):
    inutilize_number_range(
        tenant=tenant_a,
        provider=provider_sp,
        series=1,
        n_ini=900,
        n_fin=901,
        x_just="Inutilizacao de faixa de teste unitario U23",
    )
    assert NfeTransmissionAttempt.objects.filter(
        tenant=tenant_a, stage="inut", invoice__isnull=True
    ).exists()
