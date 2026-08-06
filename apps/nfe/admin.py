from django.contrib import admin

from apps.nfe.models import (
    NfeInvoice,
    NfeInvoiceEvent,
    NfeInvoiceItem,
    NfeNumberSeries,
    NfeProduct,
)


class NfeInvoiceItemInline(admin.TabularInline):
    model = NfeInvoiceItem
    extra = 0


@admin.register(NfeProduct)
class NfeProductAdmin(admin.ModelAdmin):
    list_display = ("code", "description", "ncm", "unit_price_cents", "is_active", "tenant")
    list_filter = ("is_active",)
    search_fields = ("code", "description", "ncm")


@admin.register(NfeNumberSeries)
class NfeNumberSeriesAdmin(admin.ModelAdmin):
    list_display = ("provider", "series", "tp_amb", "next_number", "is_active", "tenant")


@admin.register(NfeInvoice)
class NfeInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "series",
        "number",
        "status",
        "total_cents",
        "provider",
        "customer",
        "tenant",
        "created_at",
    )
    list_filter = ("status", "tp_amb")
    search_fields = ("idempotency_key", "access_key", "protocol")
    inlines = [NfeInvoiceItemInline]
    readonly_fields = ("correlation_id", "payload_hash", "fiscal_snapshot", "created_at", "updated_at")


@admin.register(NfeInvoiceEvent)
class NfeInvoiceEventAdmin(admin.ModelAdmin):
    list_display = ("invoice", "from_status", "to_status", "actor", "occurred_at")
    list_filter = ("to_status",)
