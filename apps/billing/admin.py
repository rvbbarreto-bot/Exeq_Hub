from django.contrib import admin

from apps.billing.models import Charge, PaymentEvent, WebhookInbox
from shared.money import format_brl_from_cents


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("idempotency_key", "status", "amount_brl", "gateway_ref", "tenant")
    list_filter = ("status", "billing_type")
    search_fields = ("idempotency_key", "gateway_ref", "digitable_line")
    readonly_fields = ("amount_brl", "correlation_id", "gateway_payload")

    @admin.display(description="Valor", ordering="amount_cents")
    def amount_brl(self, obj: Charge) -> str:
        return format_brl_from_cents(obj.amount_cents)


@admin.register(WebhookInbox)
class WebhookInboxAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "idempotency_key",
        "status",
        "signature_valid",
        "tenant",
        "processed_at",
    )
    list_filter = ("provider", "status", "signature_valid")
    search_fields = ("idempotency_key", "payload_hash")
    readonly_fields = ("payload_hash", "processed_at")


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("charge", "amount_brl", "paid_at", "gateway_ref", "tenant")
    list_filter = ("paid_at",)
    search_fields = ("gateway_ref",)
    readonly_fields = ("amount_brl", "created_at")

    @admin.display(description="Valor", ordering="amount_cents")
    def amount_brl(self, obj: PaymentEvent) -> str:
        return format_brl_from_cents(obj.amount_cents)
