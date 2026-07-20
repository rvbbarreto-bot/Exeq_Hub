from django.contrib import admin

from apps.accounts.models import (
    CertificateAudit,
    DigitalCertificate,
    ElectronicProxy,
    Tenant,
    TenantMembership,
    TenantRole,
    TenantSecret,
    User,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("slug", "legal_name", "document", "status", "focus_layout")
    search_fields = ("slug", "legal_name", "document")
    list_filter = ("status", "focus_layout")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "is_active", "is_platform_admin")
    search_fields = ("email", "name")
    exclude = ("password",)


@admin.register(TenantRole)
class TenantRoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_system")
    search_fields = ("code", "name")


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("tenant", "user", "role", "is_active")
    list_filter = ("is_active", "role")
    autocomplete_fields = ("tenant", "user", "role")


@admin.register(TenantSecret)
class TenantSecretAdmin(admin.ModelAdmin):
    list_display = ("tenant", "provider", "key_name", "key_version")
    exclude = ("ciphertext",)
    list_filter = ("provider", "tenant")
    search_fields = ("key_name", "provider")
    autocomplete_fields = ("tenant",)


@admin.register(DigitalCertificate)
class DigitalCertificateAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "cnpj",
        "cert_type",
        "is_primary",
        "status",
        "not_after",
        "tenant",
    )
    list_filter = ("status", "cert_type", "is_primary", "tenant")
    search_fields = ("label", "cnpj", "thumbprint_sha256")
    readonly_fields = (
        "thumbprint_sha256",
        "not_before",
        "not_after",
        "stored_file",
        "password_secret",
        "version",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("tenant", "provider")


@admin.register(CertificateAudit)
class CertificateAuditAdmin(admin.ModelAdmin):
    list_display = ("certificate", "action", "created_at", "tenant")
    list_filter = ("action",)
    search_fields = ("certificate__cnpj", "certificate__label")


@admin.register(ElectronicProxy)
class ElectronicProxyAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "principal_cnpj",
        "proxy_document",
        "status",
        "valid_from",
        "valid_to",
        "tenant",
    )
    list_filter = ("status", "proxy_document_type", "tenant")
    search_fields = ("principal_cnpj", "proxy_document", "label")
    autocomplete_fields = ("tenant", "provider")
