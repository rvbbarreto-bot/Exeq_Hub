"""NFC-e — cancelamento stub + artefato PDF cancelado."""

from __future__ import annotations

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceArtifact, NfceInvoice
from apps.nfce.services import (
    cancel_nfce,
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


def _authorized_invoice(nfce_settings, tenant_a, provider_sp):
    product = create_product(
        tenant=tenant_a,
        code="CAN1",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        idempotency_key="nfce-cancel-1",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    assert validate_invoice(inv)["ok"] is True
    emit_nfce(inv)
    inv.refresh_from_db()
    assert inv.status == NfceInvoice.Status.AUTHORIZED
    return inv


@pytest.mark.django_db
def test_cancel_nfce_stub(nfce_settings, tenant_a, provider_sp):
    inv = _authorized_invoice(nfce_settings, tenant_a, provider_sp)
    cancel_nfce(
        inv,
        justificativa="Cancelamento de teste homologacao PDV",
        actor="test",
    )
    inv.refresh_from_db()
    assert inv.status == NfceInvoice.Status.CANCELLED
    art = NfceArtifact.objects.get(invoice=inv, kind=NfceArtifact.Kind.DANFE_PDF)
    from apps.nfce.artifacts import read_artifact_bytes

    pdf = read_artifact_bytes(art)
    assert pdf.startswith(b"%PDF")


@pytest.mark.django_db
def test_cancel_short_justificativa_rejected(nfce_settings, tenant_a, provider_sp):
    inv = _authorized_invoice(nfce_settings, tenant_a, provider_sp)
    from apps.nfce.exceptions import NfceValidationError

    with pytest.raises(NfceValidationError):
        cancel_nfce(inv, justificativa="curta")
