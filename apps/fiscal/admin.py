from django.contrib import admin, messages

from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.fiscal.tax_engine import publish_catalog


@admin.register(FiscalProfile)
class FiscalProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "tax_regime", "tenant", "status")
    list_filter = ("tax_regime", "status", "tenant")
    search_fields = ("name",)
    autocomplete_fields = ("tenant",)


class MunicipalTaxRuleInline(admin.TabularInline):
    model = MunicipalTaxRule
    extra = 0
    fields = (
        "ibge_code",
        "service_code",
        "tax_regime",
        "iss_rate",
        "fiscal_profile",
        "valid_from",
        "valid_to",
    )
    autocomplete_fields = ("fiscal_profile",)


@admin.register(TaxRuleCatalog)
class TaxRuleCatalogAdmin(admin.ModelAdmin):
    list_display = ("version", "status", "tenant", "published_at")
    list_filter = ("status", "tenant")
    search_fields = ("version",)
    autocomplete_fields = ("tenant",)
    inlines = [MunicipalTaxRuleInline]
    actions = ("action_publish",)

    @admin.action(description="Publicar catálogo (checklist completo)")
    def action_publish(self, request, queryset):
        for catalog in queryset:
            try:
                publish_catalog(catalog)
                messages.success(request, f"Catálogo v{catalog.version} publicado.")
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f"v{catalog.version}: {exc}")


@admin.register(MunicipalTaxRule)
class MunicipalTaxRuleAdmin(admin.ModelAdmin):
    list_display = (
        "ibge_code",
        "service_code",
        "tax_regime",
        "iss_rate",
        "catalog",
        "fiscal_profile",
        "tenant",
    )
    list_filter = ("ibge_code", "tax_regime", "tenant")
    search_fields = ("ibge_code", "service_code", "municipio_nome")
    autocomplete_fields = ("tenant", "catalog", "fiscal_profile")
