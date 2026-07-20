from django.contrib import admin

from apps.das.models import GuiaFiscal


@admin.register(GuiaFiscal)
class GuiaFiscalAdmin(admin.ModelAdmin):
    list_display = (
        "tipo_guia",
        "competencia",
        "status",
        "compliance_status",
        "valor_total",
        "provider",
        "tenant",
    )
    list_filter = ("tipo_guia", "status", "compliance_status")
    autocomplete_fields = ("tenant", "provider", "pdf_file")
    readonly_fields = ("valor_total", "pdf_storage_key", "created_at", "updated_at")
