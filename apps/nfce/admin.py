"""Admin NFC-e — CSC, séries, cupons."""

from django.contrib import admin

from apps.nfce.models import (
    NfceArtifact,
    NfceInvoice,
    NfceInvoiceEvent,
    NfceInvoiceItem,
    NfceNumberSeries,
    TenantCscToken,
)


class NfceInvoiceItemInline(admin.TabularInline):
    model = NfceInvoiceItem
    extra = 0
    readonly_fields = ("line_number", "code", "description", "total_cents")


@admin.register(TenantCscToken)
class TenantCscTokenAdmin(admin.ModelAdmin):
    list_display = ("provider", "tp_amb", "csc_id", "csc_token_masked", "is_active", "tenant")
    list_filter = ("tp_amb", "is_active")
    search_fields = ("provider__document", "provider__legal_name", "csc_id", "tenant__slug")
    autocomplete_fields = ("tenant", "provider")

    @admin.display(description="Token CSC")
    def csc_token_masked(self, obj: TenantCscToken) -> str:
        tok = (obj.csc_token or "").strip()
        if len(tok) <= 4:
            return "****"
        return f"{tok[:2]}…{tok[-2:]}"


@admin.register(NfceNumberSeries)
class NfceNumberSeriesAdmin(admin.ModelAdmin):
    list_display = ("provider", "series", "tp_amb", "next_number", "is_active", "tenant")
    list_filter = ("tp_amb", "is_active")
    search_fields = ("provider__document", "tenant__slug")


@admin.register(NfceInvoice)
class NfceInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "series",
        "number",
        "status",
        "access_key",
        "total_cents",
        "provider",
        "tenant",
        "created_at",
    )
    list_filter = ("status", "tp_amb")
    search_fields = ("access_key", "idempotency_key", "protocol")
    readonly_fields = (
        "access_key",
        "protocol",
        "fiscal_snapshot",
        "taxes_summary",
        "payload_hash",
        "correlation_id",
    )
    inlines = (NfceInvoiceItemInline,)


@admin.register(NfceArtifact)
class NfceArtifactAdmin(admin.ModelAdmin):
    list_display = ("invoice", "kind", "checksum_sha256", "tenant", "created_at")
    list_filter = ("kind",)
    readonly_fields = ("checksum_sha256", "stored_file")


@admin.register(NfceInvoiceEvent)
class NfceInvoiceEventAdmin(admin.ModelAdmin):
    list_display = ("invoice", "from_status", "to_status", "actor", "occurred_at")
    list_filter = ("to_status",)
    readonly_fields = ("metadata",)
