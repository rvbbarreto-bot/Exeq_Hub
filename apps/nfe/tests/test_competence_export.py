"""Export competência NF-e (ACC-01)."""

from __future__ import annotations

import pytest

from apps.accounts.models import Tenant
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.competence_export import export_competence_package
from apps.nfe.models import NfeInvoice
from apps.nfe.services import create_draft, emit_invoice, replace_items
from apps.nfe.services import create_product


@pytest.fixture
def export_tenant(db, settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    tenant = Tenant.objects.create(
        slug="nfe-export",
        legal_name="Export Test",
        document="60746948000112",
        settings={"nfe_enabled": True},
    )
    return tenant


@pytest.mark.django_db
def test_export_competence_manifest(export_tenant, settings, tmp_path):
    settings.NFE_ENABLED = True
    tenant = export_tenant
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="Emit",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )
    customer = Customer.objects.create(
        tenant=tenant,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente",
        address={
            "logradouro": "Av B",
            "numero": "2",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )
    product = create_product(
        tenant=tenant,
        code="EXP1",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant,
        provider=provider,
        customer=customer,
        idempotency_key="exp-1",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    inv = emit_invoice(inv)
    assert inv.status == NfeInvoice.Status.AUTHORIZED

    result = export_competence_package(
        tenant_id=tenant.id,
        year=inv.issue_date.year,
        month=inv.issue_date.month,
        out_dir=tmp_path,
    )
    assert result["count"] == 1
    from pathlib import Path

    assert Path(result["path"]).exists()
