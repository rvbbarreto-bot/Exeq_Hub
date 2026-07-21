from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

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
from apps.billing.exceptions import (
    InvalidPaymentProviderError,
    InvalidProviderCredentialsError,
)
from apps.billing.provider_services import (
    get_billing_provider_status,
    get_inter_credentials_metadata,
    get_token_provider_metadata,
    save_inter_credentials,
    save_token_provider_credentials,
    set_billing_provider,
    test_inter_connection,
)
from integrations.payments.router import (
    KNOWN_PAYMENT_PROVIDERS,
    PROVIDER_ASAAS,
    PROVIDER_C6,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "slug",
        "legal_name",
        "document",
        "status",
        "focus_layout",
        "billing_provider_link",
    )
    search_fields = ("slug", "legal_name", "document")
    list_filter = ("status", "focus_layout")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/billing-provider/",
                self.admin_site.admin_view(self.billing_provider_view),
                name="accounts_tenant_billing_provider",
            ),
        ]
        return custom + urls

    @admin.display(description="Cobrança")
    def billing_provider_link(self, obj: Tenant) -> str:
        from django.utils.html import format_html

        url = reverse("admin:accounts_tenant_billing_provider", args=[obj.pk])
        return format_html('<a href="{}">Configurar provedor</a>', url)

    def billing_provider_view(self, request, object_id):
        tenant = self.get_object(request, object_id)
        if tenant is None:
            return self._get_obj_not_found_redirect(
                request, self.model._meta, object_id
            )

        if request.method == "POST":
            action = request.POST.get("action")
            try:
                if action == "set_provider":
                    set_billing_provider(
                        tenant=tenant,
                        provider=request.POST.get("provider") or "",
                        actor_user=request.user,
                    )
                    messages.success(request, "Provedor de cobrança atualizado.")
                elif action == "save_inter":
                    cert = request.FILES.get("cert_file")
                    key = request.FILES.get("key_file")
                    cert_pem = cert.read().decode("utf-8", errors="replace") if cert else ""
                    key_pem = key.read().decode("utf-8", errors="replace") if key else ""
                    save_inter_credentials(
                        tenant=tenant,
                        client_id=request.POST.get("client_id") or "",
                        client_secret=request.POST.get("client_secret") or "",
                        cert_pem=cert_pem,
                        key_pem=key_pem,
                        conta_corrente=request.POST.get("conta_corrente") or "",
                        actor_user=request.user,
                    )
                    messages.success(request, "Credenciais Inter salvas.")
                elif action == "test_inter":
                    result = test_inter_connection(
                        tenant=tenant, actor_user=request.user
                    )
                    if result.get("status") == "ok":
                        messages.success(request, "Conexão Inter OK.")
                    else:
                        messages.error(
                            request,
                            f"Falha na conexão Inter: {result.get('detail') or 'erro'}",
                        )
                elif action == "save_asaas":
                    save_token_provider_credentials(
                        tenant=tenant,
                        provider=PROVIDER_ASAAS,
                        api_token=request.POST.get("api_token") or "",
                        actor_user=request.user,
                    )
                    messages.success(request, "Credenciais Asaas salvas.")
                elif action == "save_c6":
                    save_token_provider_credentials(
                        tenant=tenant,
                        provider=PROVIDER_C6,
                        api_token=request.POST.get("api_token") or "",
                        actor_user=request.user,
                    )
                    messages.success(request, "Credenciais C6 salvas.")
            except (InvalidPaymentProviderError, InvalidProviderCredentialsError) as exc:
                messages.error(request, str(exc))
            return HttpResponseRedirect(
                reverse("admin:accounts_tenant_billing_provider", args=[tenant.pk])
            )

        context = {
            **self.admin_site.each_context(request),
            "title": "Provedor de cobrança",
            "tenant": tenant,
            "status": get_billing_provider_status(tenant=tenant),
            "providers": sorted(KNOWN_PAYMENT_PROVIDERS),
            "inter": get_inter_credentials_metadata(tenant=tenant),
            "asaas": get_token_provider_metadata(
                tenant=tenant, provider=PROVIDER_ASAAS
            ),
            "c6": get_token_provider_metadata(tenant=tenant, provider=PROVIDER_C6),
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request,
            "admin/accounts/tenant/billing_provider.html",
            context,
        )


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
