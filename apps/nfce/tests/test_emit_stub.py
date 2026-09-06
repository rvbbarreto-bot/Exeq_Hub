"""NFC-e — emit stub + policy checkout."""

from __future__ import annotations

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfce.services import (
    checkout_and_emit_nfce,
    create_draft,
    emit_nfce,
    replace_items,
    validate_invoice,
)
from apps.nfe.services import create_product


@pytest.fixture
def nfce_settings(settings, tenant_a):
    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "stub"
    tenant_a.settings = apply_emission_flags(
        tenant_a.settings, nfse=True, nfe=True, nfce=True
    )
    tenant_a.save(update_fields=["settings", "updated_at"])
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ PDV LAB",
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
        is_active=True,
    )


@pytest.mark.django_db
def test_emit_anonymous_nfce_stub(nfce_settings, tenant_a, provider_sp):
    product = create_product(
        tenant=tenant_a,
        code="PDV1",
        description="Item balcão",
        ncm="21069090",
        unit_price_cents=5000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        idempotency_key="nfce-lab-1",
        omit_dest=True,
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "2"}])
    inv.refresh_from_db()
    result = validate_invoice(inv)
    assert result["ok"] is True
    assert result["totals"]["total_cents"] == 10_000

    emit_nfce(inv)
    inv.refresh_from_db()
    assert inv.status == NfceInvoice.Status.AUTHORIZED
    assert inv.number == 1
    assert len(inv.access_key) == 44
    assert inv.fiscal_snapshot["header"]["model"] == "65"
    assert "dh_emi" in inv.fiscal_snapshot["header"]
    assert "T12:00:00" not in inv.fiscal_snapshot["header"]["dh_emi"]
    assert inv.fiscal_snapshot["sefaz"]["dh_recbto"]
    from apps.nfce.models import NfceArtifact

    assert NfceArtifact.objects.filter(
        invoice=inv, kind=NfceArtifact.Kind.XML_AUTHORIZED
    ).exists()
    assert NfceArtifact.objects.filter(
        invoice=inv, kind=NfceArtifact.Kind.DANFE_PDF
    ).exists()


@pytest.mark.django_db
def test_checkout_payment_method_persisted(nfce_settings, tenant_a, provider_sp):
    product = create_product(
        tenant=tenant_a,
        code="PAY",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = checkout_and_emit_nfce(
        tenant=tenant_a,
        provider=provider_sp,
        items=[{"product_id": str(product.id), "quantity": "1"}],
        idempotency_key="nfce-pay-17",
        payment_method="17",
    )
    assert isinstance(inv, NfceInvoice)
    assert inv.payment_method == "17"
    assert inv.status == NfceInvoice.Status.AUTHORIZED


@pytest.mark.django_db
def test_checkout_cnpj_routes_nfe_not_nfce(nfce_settings, tenant_a, provider_sp):
    product = create_product(
        tenant=tenant_a,
        code="B2B",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    out = checkout_and_emit_nfce(
        tenant=tenant_a,
        provider=provider_sp,
        items=[{"product_id": str(product.id), "quantity": "1"}],
        idempotency_key="nfce-cnpj-block",
        cnpj="37229907000137",
    )
    assert out["route"] == "nfe"
    assert out["model"] == "55"
    assert NfceInvoice.objects.filter(tenant=tenant_a).count() == 0


@pytest.mark.django_db
def test_sn_without_csosn_blocks(nfce_settings, tenant_a, provider_sp):
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        idempotency_key="nfce-no-csosn",
    )
    replace_items(
        inv,
        items=[
            {
                "code": "X",
                "description": "Sem CSOSN",
                "ncm": "21069090",
                "quantity": "1",
                "unit_price_cents": 100,
                "cfop": "5102",
            }
        ],
    )
    inv.refresh_from_db()
    result = validate_invoice(inv)
    assert result["ok"] is False
    assert any("CSOSN" in e["message"] for e in result["field_errors"])
