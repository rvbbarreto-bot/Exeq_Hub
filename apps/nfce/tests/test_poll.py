"""NFC-e polling — consulta stub após lote 103."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.models import NfceInvoice
from apps.nfce.polling import poll_nfce_invoice
from apps.nfce.services import create_draft, emit_nfce, replace_items, validate_invoice
from apps.nfe.services import create_product
from integrations.sefaz_nfe.port import NfeEmitResult, StubNfeProvider


@pytest.fixture
def nfce_poll(settings, tenant_a):
    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "stub"
    settings.NFCE_SYNC_POLL = False
    tenant_a.settings = apply_emission_flags(
        tenant_a.settings, nfse=True, nfe=True, nfce=True
    )
    tenant_a.save(update_fields=["settings"])
    return tenant_a


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="Poll Lab",
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


class PollingStub(StubNfeProvider):
    def consultar(self, **kwargs):
        return NfeEmitResult(
            status="authorized",
            access_key=kwargs.get("access_key") or "",
            protocol="STUBPOLL123",
        )


@pytest.mark.django_db
def test_poll_nfce_resolves_to_authorized(nfce_poll, tenant_a, provider_sp):
    product = create_product(
        tenant=tenant_a,
        code="P1",
        description="Item",
        ncm="21069090",
        unit_price_cents=500,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        idempotency_key="nfce-poll-1",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    assert validate_invoice(inv)["ok"]
    emit_nfce(inv)
    inv.refresh_from_db()
    snap = dict(inv.fiscal_snapshot or {})
    snap["sefaz"] = {"n_rec": "999888777666555", "poll_attempts": 0}
    inv.fiscal_snapshot = snap
    inv.status = NfceInvoice.Status.POLLING
    inv.number_consumed = True
    inv.save(update_fields=["fiscal_snapshot", "status", "number_consumed", "updated_at"])

    with patch("apps.nfce.polling.get_nfce_provider", return_value=PollingStub()):
        poll_nfce_invoice(inv)

    inv.refresh_from_db()
    assert inv.status == NfceInvoice.Status.AUTHORIZED
    assert inv.protocol == "STUBPOLL123"
