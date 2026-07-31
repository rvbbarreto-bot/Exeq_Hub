"""Regressão: labels PT-BR e default Inter no Admin Cobrança (plano Admin PT)."""

from django.contrib import admin

from apps.billing.admin import PaymentEventAdmin, WebhookInboxAdmin
from apps.billing.models import PaymentEvent, WebhookInbox


def test_webhook_inbox_verbose_names_pt():
    assert WebhookInbox._meta.verbose_name == "Caixa de entrada de webhook"
    assert WebhookInbox._meta.verbose_name_plural == "Caixas de entrada de webhook"
    expected = {
        "provider": "Provedor",
        "idempotency_key": "Chave de idempotência",
        "status": "Status",
        "signature": "Assinatura",
        "signature_valid": "Assinatura válida",
        "raw_payload": "Payload bruto",
        "payload_hash": "Hash do payload",
        "error_message": "Mensagem de erro",
        "processed_at": "Processado em",
    }
    for name, label in expected.items():
        assert WebhookInbox._meta.get_field(name).verbose_name == label


def test_webhook_inbox_provider_choices_default_inter():
    field = WebhookInbox._meta.get_field("provider")
    assert field.default == WebhookInbox.Provider.INTER
    assert field.default == "inter"
    codes = {c[0] for c in field.choices}
    assert codes == {"inter", "asaas", "c6"}
    assert WebhookInbox().provider == "inter"


def test_payment_event_verbose_names_pt():
    assert PaymentEvent._meta.verbose_name == "Evento de pagamento"
    assert PaymentEvent._meta.verbose_name_plural == "Eventos de pagamento"
    expected = {
        "tenant": "Tenant",
        "charge": "Cobrança",
        "webhook_inbox": "Caixa de entrada de webhook",
        "amount_cents": "Valor",
        "paid_at": "Pago em",
        "gateway_ref": "Referência gateway",
        "metadata": "Metadados",
        "created_at": "Criado em",
    }
    for name, label in expected.items():
        assert PaymentEvent._meta.get_field(name).verbose_name == label


def test_admin_registers_inbox_and_payment_event():
    assert admin.site.is_registered(WebhookInbox)
    assert admin.site.is_registered(PaymentEvent)
    inbox_admin = admin.site._registry[WebhookInbox]
    assert isinstance(inbox_admin, WebhookInboxAdmin)
    assert "provider" in inbox_admin.list_display
    assert "provider" in inbox_admin.list_filter
    # Select vem das choices do model (não CharField livre).
    assert WebhookInbox._meta.get_field("provider").choices
    pe_admin = admin.site._registry[PaymentEvent]
    assert isinstance(pe_admin, PaymentEventAdmin)
    assert pe_admin.amount_brl.short_description == "Valor"
