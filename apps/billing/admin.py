from django.contrib import admin

from apps.billing.models import Charge, PaymentEvent, WebhookInbox


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ("idempotency_key", "status", "amount_cents", "gateway_ref", "tenant")
    list_filter = ("status",)


@admin.register(WebhookInbox)
class WebhookInboxAdmin(admin.ModelAdmin):
    list_display = ("provider", "idempotency_key", "status", "signature_valid", "tenant")


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("charge", "amount_cents", "paid_at", "gateway_ref")
