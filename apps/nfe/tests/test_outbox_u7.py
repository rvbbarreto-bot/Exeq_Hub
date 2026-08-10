"""U7 RF-70 — outbox nfe.authorized / rejected / cancelled."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.channel.models import ChannelNotification
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice
from apps.nfe.services import (
    cancel_invoice,
    create_draft,
    create_product,
    emit_invoice,
    replace_items,
)
from apps.ops.dispatcher import claim_and_dispatch
from apps.ops.models import OutboxMessage


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


def _draft_with_item(tenant, provider, customer):
    product = create_product(
        tenant=tenant,
        code="OUT1",
        description="Item outbox",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant,
        provider=provider,
        customer=customer,
        idempotency_key="u7-outbox-" + str(product.id)[:8],
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    return inv


@pytest.mark.django_db
def test_emit_stub_enqueues_nfe_authorized(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _draft_with_item(tenant_a, provider_sp, customer_b2b)
    emit_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    msg = OutboxMessage.objects.get(
        tenant=tenant_a, event_type="nfe.authorized", aggregate_id=inv.id
    )
    assert msg.aggregate_type == "nfe_invoice"
    assert msg.payload.get("schema_version") == 1
    assert msg.payload.get("access_key") == inv.access_key
    assert str(msg.correlation_id) == str(inv.correlation_id)


@pytest.mark.django_db
def test_cancel_enqueues_nfe_cancelled(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _draft_with_item(tenant_a, provider_sp, customer_b2b)
    emit_invoice(inv)
    inv.refresh_from_db()
    cancel_invoice(
        inv,
        justificativa="Cancelamento de teste lab outbox RF-70",
        actor="test",
    )
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.CANCELLED
    assert OutboxMessage.objects.filter(
        tenant=tenant_a, event_type="nfe.cancelled", aggregate_id=inv.id
    ).exists()


@pytest.mark.django_db
def test_dispatcher_nfe_authorized_notifies(tenant_a):
    tenant_a.settings = {"notify_phone": "+5511999999999"}
    tenant_a.save(update_fields=["settings"])
    msg = OutboxMessage.objects.create(
        tenant=tenant_a,
        event_type="nfe.authorized",
        aggregate_type="nfe_invoice",
        aggregate_id=tenant_a.id,
        payload={
            "schema_version": 1,
            "access_key": "35260837229907000137550010000000011000000010",
            "series": 1,
            "number": 10,
        },
        available_at=timezone.now(),
    )
    assert claim_and_dispatch(str(msg.id)) == "processed"
    note = ChannelNotification.objects.get(
        tenant=tenant_a, event_type="nfe.authorized"
    )
    assert note.status == ChannelNotification.Status.SENT
    assert "NF-e autorizada" in note.message_body


@pytest.mark.django_db
def test_dispatcher_nfe_rejected_and_cancelled_bodies(tenant_a):
    tenant_a.settings = {"notify_phone": "+5511999999999"}
    tenant_a.save(update_fields=["settings"])
    for event, snippet in (
        ("nfe.rejected", "rejeitada"),
        ("nfe.cancelled", "cancelada"),
    ):
        msg = OutboxMessage.objects.create(
            tenant=tenant_a,
            event_type=event,
            aggregate_type="nfe_invoice",
            aggregate_id=tenant_a.id,
            payload={"series": 1, "number": 2, "rejection_code": "204"},
            available_at=timezone.now(),
        )
        assert claim_and_dispatch(str(msg.id)) == "processed"
        note = ChannelNotification.objects.filter(
            tenant=tenant_a, event_type=event
        ).latest("created_at")
        assert snippet in note.message_body.lower()


@pytest.mark.django_db
def test_nfe_outbox_noop_without_phone(tenant_a):
    msg = OutboxMessage.objects.create(
        tenant=tenant_a,
        event_type="nfe.authorized",
        aggregate_type="nfe_invoice",
        aggregate_id=tenant_a.id,
        payload={"number": 1, "series": 1},
        available_at=timezone.now(),
    )
    assert claim_and_dispatch(str(msg.id)) == "processed"
    assert ChannelNotification.objects.filter(tenant=tenant_a).count() == 0
