from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from apps.master_data.models import (
    Customer,
    NationalServiceCatalogVersion,
    NationalServiceItem,
    NbsCatalogVersion,
    NbsItem,
    Provider,
    ServiceCatalogItem,
)
from apps.accounts.models import Tenant
from apps.master_data.national_service_import import (
    NationalServiceImportError,
    import_national_service_xlsx,
    materialize_national_services_for_tenant,
    publish_national_service_version,
)
from apps.master_data.nbs_import import NbsImportError, import_nbs_xlsx, publish_nbs_version


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = (
        "legal_name",
        "document",
        "tax_regime",
        "data_source",
        "tenant",
        "is_active",
    )
    list_filter = ("is_active", "tax_regime", "data_source", "tenant")
    search_fields = ("legal_name", "document", "municipal_registration")
    autocomplete_fields = ("tenant",)
    readonly_fields = ("last_lookup_at", "receita_raw_payload")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "document",
        "document_type",
        "data_source",
        "tenant",
        "is_active",
    )
    list_filter = ("document_type", "is_active", "data_source", "tenant")
    search_fields = ("name", "document", "email")
    autocomplete_fields = ("tenant",)
    readonly_fields = ("last_lookup_at", "receita_raw_payload")


class AnexoBImportForm(forms.Form):
    version_label = forms.CharField(
        max_length=64,
        label="Rótulo da versão",
        help_text="Ex.: 2026-01-22 — único no sistema.",
    )
    xlsx_file = forms.FileField(
        label="Arquivo XLSX (Anexo B)",
        help_text="Aba LISTA.SERV.NAC. — Código de Tributação Nacional.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Observações",
    )
    publish = forms.BooleanField(
        required=False,
        initial=True,
        label="Publicar como versão ativa",
        help_text="Substitui a versão publicada anterior (fica 'Substituída').",
    )


class NbsImportForm(forms.Form):
    version_label = forms.CharField(
        max_length=64,
        label="Rótulo da versão",
        help_text="Ex.: NBS_v2.0-2026-01-22 — único no sistema.",
    )
    xlsx_file = forms.FileField(
        label="Arquivo XLSX (Anexo B — NBS)",
        help_text="Aba LISTA.NBS* — Lista NBS nacional.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Observações",
    )
    publish = forms.BooleanField(
        required=False,
        initial=True,
        label="Publicar como versão ativa",
    )


class MaterializeNationalServicesForm(forms.Form):
    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.order_by("slug"),
        label="Tenant",
        help_text="Catálogo de serviços deste tenant (campo Serviço da emissão NFS-e).",
    )
    only_missing = forms.BooleanField(
        required=False,
        initial=True,
        label="Somente códigos ainda inexistentes",
        help_text=(
            "Marcado: cria só o que falta. "
            "Desmarcado: também atualiza descrição/LC dos já existentes."
        ),
    )


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
    change_list_template = "admin/master_data/servicecatalogitem/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "import-anexo-b/",
                self.admin_site.admin_view(self.import_anexo_b_view),
                name="master_data_servicecatalogitem_import_anexo_b",
            ),
            path(
                "materializar-lista-nacional/",
                self.admin_site.admin_view(self.materialize_national_view),
                name="master_data_servicecatalogitem_materialize_national",
            ),
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        published = (
            NationalServiceCatalogVersion.objects.filter(
                status=NationalServiceCatalogVersion.Status.PUBLISHED
            )
            .order_by("-published_at")
            .first()
        )
        extra_context["national_version"] = published
        extra_context["import_anexo_b_url"] = reverse(
            "admin:master_data_servicecatalogitem_import_anexo_b"
        )
        extra_context["materialize_national_url"] = reverse(
            "admin:master_data_servicecatalogitem_materialize_national"
        )
        return super().changelist_view(request, extra_context=extra_context)

    def import_anexo_b_view(self, request):
        if not request.user.is_staff:
            messages.error(request, "Sem permissão.")
            return HttpResponseRedirect(
                reverse("admin:master_data_servicecatalogitem_changelist")
            )

        form = AnexoBImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            upload = form.cleaned_data["xlsx_file"]
            from pathlib import Path
            import tempfile

            suffix = Path(upload.name).suffix or ".xlsx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in upload.chunks():
                    tmp.write(chunk)
                tmp_path = Path(tmp.name)
            try:
                version = import_national_service_xlsx(
                    path=tmp_path,
                    version_label=form.cleaned_data["version_label"],
                    publish=bool(form.cleaned_data.get("publish")),
                    notes=form.cleaned_data.get("notes") or "",
                )
            except NationalServiceImportError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Importação OK: versão {version.version_label} "
                    f"({version.row_count} códigos, status={version.status}).",
                )
                return HttpResponseRedirect(
                    reverse(
                        "admin:master_data_nationalservicecatalogversion_change",
                        args=[version.pk],
                    )
                )
            finally:
                tmp_path.unlink(missing_ok=True)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "title": "Importar Anexo B — Lista Serviço Nacional",
        }
        return TemplateResponse(
            request,
            "admin/master_data/servicecatalogitem/import_anexo_b.html",
            context,
        )

    def materialize_national_view(self, request):
        if not request.user.is_staff:
            messages.error(request, "Sem permissão.")
            return HttpResponseRedirect(
                reverse("admin:master_data_servicecatalogitem_changelist")
            )

        form = MaterializeNationalServicesForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                result = materialize_national_services_for_tenant(
                    tenant=form.cleaned_data["tenant"],
                    only_missing=bool(form.cleaned_data.get("only_missing")),
                )
            except NationalServiceImportError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    (
                        f"Materialização OK (versão {result['version']}): "
                        f"{result['created']} criados, {result['updated']} atualizados, "
                        f"{result['skipped']} ignorados "
                        f"(lista nacional: {result['total_national']})."
                    ),
                )
                return HttpResponseRedirect(
                    reverse("admin:master_data_servicecatalogitem_changelist")
                    + f"?tenant__id__exact={form.cleaned_data['tenant'].pk}"
                )

        published = (
            NationalServiceCatalogVersion.objects.filter(
                status=NationalServiceCatalogVersion.Status.PUBLISHED
            )
            .order_by("-published_at")
            .first()
        )
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "national_version": published,
            "title": "Materializar Lista Nacional no tenant",
        }
        return TemplateResponse(
            request,
            "admin/master_data/servicecatalogitem/materialize_national.html",
            context,
        )


@admin.register(NationalServiceCatalogVersion)
class NationalServiceCatalogVersionAdmin(admin.ModelAdmin):
    list_display = (
        "version_label",
        "status",
        "row_count",
        "source_filename",
        "imported_at",
        "published_at",
        "items_link",
    )
    list_filter = ("status",)
    search_fields = ("version_label", "source_filename", "notes")
    readonly_fields = (
        "source_filename",
        "sheet_name",
        "row_count",
        "imported_at",
        "published_at",
    )
    actions = ("action_publish",)

    @admin.display(description="Códigos")
    def items_link(self, obj):
        url = (
            reverse("admin:master_data_nationalserviceitem_changelist")
            + f"?version__id__exact={obj.pk}"
        )
        return format_html('<a href="{}">{} itens</a>', url, obj.row_count)

    @admin.action(description="Publicar versões selecionadas")
    def action_publish(self, request, queryset):
        for version in queryset.order_by("imported_at"):
            publish_national_service_version(version)
        self.message_user(request, "Versão(ões) publicada(s).", messages.SUCCESS)


@admin.register(NationalServiceItem)
class NationalServiceItemAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "lc116_hint",
        "item",
        "subitem",
        "desdobro",
        "short_description",
        "version",
    )
    list_filter = ("version", "item")
    search_fields = ("codigo", "description", "lc116_hint")
    readonly_fields = (
        "version",
        "codigo",
        "item",
        "subitem",
        "desdobro",
        "description",
        "lc116_hint",
    )

    @admin.display(description="Descrição")
    def short_description(self, obj):
        text = obj.description or ""
        return text if len(text) <= 80 else text[:77] + "…"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(NbsCatalogVersion)
class NbsCatalogVersionAdmin(admin.ModelAdmin):
    list_display = (
        "version_label",
        "status",
        "row_count",
        "source_filename",
        "imported_at",
        "published_at",
        "items_link",
    )
    list_filter = ("status",)
    search_fields = ("version_label", "source_filename", "notes")
    readonly_fields = (
        "source_filename",
        "sheet_name",
        "row_count",
        "imported_at",
        "published_at",
    )
    actions = ("action_publish",)
    change_list_template = "admin/master_data/nbscatalogversion/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "import-anexo-b-nbs/",
                self.admin_site.admin_view(self.import_nbs_view),
                name="master_data_nbscatalogversion_import_nbs",
            ),
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_nbs_url"] = reverse(
            "admin:master_data_nbscatalogversion_import_nbs"
        )
        return super().changelist_view(request, extra_context=extra_context)

    def import_nbs_view(self, request):
        if not request.user.is_staff:
            messages.error(request, "Sem permissão.")
            return HttpResponseRedirect(
                reverse("admin:master_data_nbscatalogversion_changelist")
            )

        form = NbsImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            from pathlib import Path
            import tempfile

            upload = form.cleaned_data["xlsx_file"]
            suffix = Path(upload.name).suffix or ".xlsx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in upload.chunks():
                    tmp.write(chunk)
                tmp_path = Path(tmp.name)
            try:
                version = import_nbs_xlsx(
                    path=tmp_path,
                    version_label=form.cleaned_data["version_label"],
                    publish=bool(form.cleaned_data.get("publish")),
                    notes=form.cleaned_data.get("notes") or "",
                )
            except NbsImportError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"Importação NBS OK: versão {version.version_label} "
                    f"({version.row_count} códigos, status={version.status}).",
                )
                return HttpResponseRedirect(
                    reverse(
                        "admin:master_data_nbscatalogversion_change",
                        args=[version.pk],
                    )
                )
            finally:
                tmp_path.unlink(missing_ok=True)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "title": "Importar Anexo B — Lista NBS",
        }
        return TemplateResponse(
            request,
            "admin/master_data/nbscatalogversion/import_nbs.html",
            context,
        )

    @admin.display(description="Códigos")
    def items_link(self, obj):
        url = (
            reverse("admin:master_data_nbsitem_changelist")
            + f"?version__id__exact={obj.pk}"
        )
        return format_html('<a href="{}">{} itens</a>', url, obj.row_count)

    @admin.action(description="Publicar versões selecionadas")
    def action_publish(self, request, queryset):
        for version in queryset.order_by("imported_at"):
            publish_nbs_version(version)
        self.message_user(request, "Versão(ões) NBS publicada(s).", messages.SUCCESS)


@admin.register(NbsItem)
class NbsItemAdmin(admin.ModelAdmin):
    list_display = ("codigo", "short_description", "is_active", "version")
    list_filter = ("version", "is_active")
    search_fields = ("codigo", "description")
    readonly_fields = ("version", "codigo", "description", "is_active")

    @admin.display(description="Descrição")
    def short_description(self, obj):
        text = obj.description or ""
        return text if len(text) <= 80 else text[:77] + "…"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
