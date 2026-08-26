from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.accounts.admin_user_forms import UserAddForm, UserChangeForm, UserResetPasswordForm
from apps.accounts.models import (
    CertificateAudit,
    DigitalCertificate,
    ElectronicProxy,
    Plan,
    Subscription,
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


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "sort_order", "limits")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "plan", "status", "current_period_start", "updated_at")
    list_filter = ("status", "plan")
    search_fields = ("tenant__slug", "tenant__legal_name", "plan__code")
    autocomplete_fields = ("tenant", "plan")


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "slug",
        "legal_name",
        "document",
        "status",
        "focus_layout",
        "subscription_plan",
        "billing_provider_link",
    )
    search_fields = ("slug", "legal_name", "document")
    list_filter = ("status", "focus_layout")

    @admin.display(description="Plano")
    def subscription_plan(self, obj: Tenant) -> str:
        try:
            sub = obj.subscription
        except Subscription.DoesNotExist:
            return "—"
        return f"{sub.plan.code} ({sub.get_status_display()})"

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

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs.setdefault("form", UserAddForm)
        else:
            kwargs.setdefault("form", UserChangeForm)
        return super().get_form(request, obj, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return ("reset_password_link",)
        return ()

    @admin.display(description="Senha")
    def reset_password_link(self, obj: User) -> str:
        from django.utils.html import format_html

        url = reverse("admin:accounts_user_reset_password", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Redefinir senha</a>',
            url,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/reset-password/",
                self.admin_site.admin_view(self.reset_password_view),
                name="accounts_user_reset_password",
            ),
        ]
        return custom + urls

    def reset_password_view(self, request, object_id):
        user = self.get_object(request, object_id)
        if user is None:
            return self._get_obj_not_found_redirect(
                request, self.model._meta, object_id
            )

        form = UserResetPasswordForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            user.set_password(form.cleaned_data["password1"])
            user.save(update_fields=["password"])
            messages.success(request, f"Senha de {user.email} atualizada.")
            return HttpResponseRedirect(
                reverse("admin:accounts_user_change", args=[user.pk])
            )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Redefinir senha — {user.email}",
            "user": user,
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request,
            "admin/accounts/user/reset_password.html",
            context,
        )

    def save_model(self, request, obj, form, change):
        if not change and isinstance(form, UserAddForm):
            form.save()
            return
        super().save_model(request, obj, form, change)


@admin.register(TenantRole)
class TenantRoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_system")
    search_fields = ("code", "name")


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("tenant", "user", "role", "is_active")
    list_filter = ("is_active", "role")
    autocomplete_fields = ("tenant", "user", "role")

    def save_model(self, request, obj, form, change):
        from django.core.exceptions import ValidationError

        from apps.accounts.plan_limits import PlanLimitError, assert_can_add_active_user

        if obj.is_active:
            was_active = False
            if change and obj.pk:
                was_active = (
                    TenantMembership.objects.filter(pk=obj.pk, is_active=True).exists()
                )
            if not was_active:
                try:
                    assert_can_add_active_user(obj.tenant)
                except PlanLimitError as exc:
                    raise ValidationError(str(exc)) from exc
        super().save_model(request, obj, form, change)


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
