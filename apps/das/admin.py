from django.contrib import admin

from apps.das.models import GuiaFiscal
from shared.money import format_brl


@admin.register(GuiaFiscal)
class GuiaFiscalAdmin(admin.ModelAdmin):
    list_display = (
        "tipo_guia",
        "competencia",
        "status",
        "compliance_status",
        "valor_total_brl",
        "provider",
        "tenant",
    )
    list_filter = ("tipo_guia", "status", "compliance_status")
    autocomplete_fields = ("tenant", "provider", "pdf_file")
    readonly_fields = (
        "valor_principal_brl",
        "valor_multa_brl",
        "valor_juros_brl",
        "valor_total_brl",
        "valor_total",
        "pdf_storage_key",
        "created_at",
        "updated_at",
    )
    fields = (
        "tenant",
        "provider",
        "tipo_guia",
        "competencia",
        "data_vencimento",
        "valor_principal_brl",
        "valor_multa_brl",
        "valor_juros_brl",
        "valor_total_brl",
        "linha_digitavel",
        "pix_copia_cola",
        "status",
        "compliance_status",
        "pdf_file",
        "pdf_storage_key",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Valor principal")
    def valor_principal_brl(self, obj: GuiaFiscal) -> str:
        return format_brl(obj.valor_principal)

    @admin.display(description="Valor multa")
    def valor_multa_brl(self, obj: GuiaFiscal) -> str:
        return format_brl(obj.valor_multa)

    @admin.display(description="Valor juros")
    def valor_juros_brl(self, obj: GuiaFiscal) -> str:
        return format_brl(obj.valor_juros)

    @admin.display(description="Valor total", ordering="valor_total")
    def valor_total_brl(self, obj: GuiaFiscal) -> str:
        return format_brl(obj.valor_total)
