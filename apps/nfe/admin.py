from django.contrib import admin

from apps.nfe.models import (
    NfeArtifact,
    NfeInutilization,
    NfeInvoice,
    NfeInvoiceEvent,
    NfeInvoiceItem,
    NfeNumberSeries,
    NfeProduct,
    NfeTransmissionAttempt,
)


class NfeInvoiceItemInline(admin.TabularInline):
    model = NfeInvoiceItem
    extra = 0


class NfeArtifactInline(admin.TabularInline):
    model = NfeArtifact
    extra = 0
    readonly_fields = ("kind", "checksum_sha256", "stored_file", "created_at")
    can_delete = False


class NfeAttemptInline(admin.TabularInline):
    model = NfeTransmissionAttempt
    extra = 0
    can_delete = False
    readonly_fields = (
        "stage",
        "result_status",
        "c_stat",
        "x_motivo",
        "http_status",
        "duration_ms",
        "created_at",
    )
    fields = readonly_fields
    ordering = ("-created_at",)
    show_change_link = True


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
        "rejection_code",
        "total_cents",
        "provider",
        "customer",
        "tenant",
        "created_at",
    )
    list_filter = ("status", "tp_amb")
    search_fields = ("idempotency_key", "access_key", "protocol", "rejection_code")
    inlines = [NfeInvoiceItemInline, NfeArtifactInline, NfeAttemptInline]
    readonly_fields = (
        "correlation_id",
        "payload_hash",
        "fiscal_snapshot",
        "last_validation",
        "created_at",
        "updated_at",
    )


@admin.register(NfeInvoiceEvent)
class NfeInvoiceEventAdmin(admin.ModelAdmin):
    list_display = ("invoice", "from_status", "to_status", "actor", "occurred_at")
    list_filter = ("to_status",)


@admin.register(NfeArtifact)
class NfeArtifactAdmin(admin.ModelAdmin):
    list_display = ("invoice", "kind", "checksum_sha256", "tenant", "created_at")


@admin.register(NfeTransmissionAttempt)
class NfeTransmissionAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "stage",
        "c_stat",
        "result_status",
        "invoice",
        "duration_ms",
        "tenant",
        "created_at",
    )
    list_filter = ("stage", "result_status")
    search_fields = ("access_key", "c_stat", "x_motivo")
    readonly_fields = (
        "invoice",
        "stage",
        "provider_kind",
        "result_status",
        "http_status",
        "c_stat",
        "x_motivo",
        "access_key",
        "duration_ms",
        "correlation_id",
        "raw",
        "created_at",
        "updated_at",
    )
