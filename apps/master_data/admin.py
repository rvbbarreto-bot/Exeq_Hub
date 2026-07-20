from django.contrib import admin

from apps.master_data.models import Customer, Provider, ServiceCatalogItem


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = (
        "legal_name",
        "document",
        "tax_regime",
        "tenant",
        "is_active",
    )
    list_filter = ("is_active", "tax_regime", "tenant")
    search_fields = ("legal_name", "document", "municipal_registration")
    autocomplete_fields = ("tenant",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "document", "document_type", "tenant", "is_active")
    list_filter = ("document_type", "is_active", "tenant")
    search_fields = ("name", "document", "email")
    autocomplete_fields = ("tenant",)


@admin.register(ServiceCatalogItem)
class ServiceCatalogItemAdmin(admin.ModelAdmin):
    list_display = (
        "service_code",
        "lc116_item",
        "codigo_tributacao_nacional_iss",
        "tenant",
        "is_active",
    )
    list_filter = ("is_active", "tenant")
    search_fields = ("service_code", "description", "codigo_tributacao_nacional_iss")
    autocomplete_fields = ("tenant",)
