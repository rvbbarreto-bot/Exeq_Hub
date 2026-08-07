from django.contrib import admin

from apps.nfe.models import (
    NfeArtifact,
    NfeInutilization,
    NfeInvoice,
    NfeInvoiceEvent,
    NfeInvoiceItem,
    NfeNumberSeries,
    NfeProduct,
)


class NfeInvoiceItemInline(admin.TabularInline):
    model = NfeInvoiceItem
    extra = 0


class NfeArtifactInline(admin.TabularInline):
    model = NfeArtifact
    extra = 0
    readonly_fields = ("kind", "checksum_sha256", "stored_file", "created_at")
    can_delete = False


@admin.register(NfeProduct)
class NfeProductAdmin(admin.ModelAdmin):
    list_display = ("code", "description", "ncm", "unit_price_cents", "is_active", "tenant")
    list_filter = ("is_active",)
    search_fields = ("code", "description", "ncm")


@admin.register(NfeNumberSeries)
class NfeNumberSeriesAdmin(admin.ModelAdmin):
    list_display = ("provider", "series", "tp_amb", "next_number", "is_active", "tenant")


@admin.register(NfeInutilization)
class NfeInutilizationAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "series",
        "tp_amb",
        "n_ini",
        "n_fin",
        "status",
        "protocol",
        "tenant",
        "created_at",
    )
    list_filter = ("status", "tp_amb")
    search_fields = ("protocol", "x_just")


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
    inlines = [NfeInvoiceItemInline, NfeArtifactInline]
    readonly_fields = ("correlation_id", "payload_hash", "fiscal_snapshot", "created_at", "updated_at")


@admin.register(NfeInvoiceEvent)
class NfeInvoiceEventAdmin(admin.ModelAdmin):
    list_display = ("invoice", "from_status", "to_status", "actor", "occurred_at")
    list_filter = ("to_status",)


@admin.register(NfeArtifact)
class NfeArtifactAdmin(admin.ModelAdmin):
    list_display = ("invoice", "kind", "checksum_sha256", "tenant", "created_at")
    list_filter = ("kind",)
