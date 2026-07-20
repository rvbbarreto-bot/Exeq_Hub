from django import forms
from django.contrib import admin, messages
from django.http import FileResponse, Http404
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.issuance.artifacts import ensure_authorized_artifacts
from apps.issuance.exceptions import (
    CancelJustificationError,
    FiscalProfileRequiredError,
    FocusCancelFailedError,
    InvalidTransitionError,
)
from apps.issuance.models import FiscalRuleSnapshot, NfArtifact, NfIssue, NfIssueEvent
from apps.issuance.polling import poll_nf_issue_status
from apps.issuance.services import cancel_nf_issue, create_nf_issue, reprocess_nf_issue
from shared.storage import StorageError, get_storage

QA_CANCEL_JUSTIFICATIVA = "Cancelamento via Django Admin QA EXEQ Hub"

_STATUS_LABELS = dict(NfIssue.Status.choices)
_ACTOR_LABELS = {
    "api": "API",
    "worker": "Processador",
    "provider": "Provedor",
    "system": "Sistema",
    "admin": "Admin",
}


def _format_occurred_at(value) -> str:
    if not value:
        return "—"
    local = timezone.localtime(value)
    ms = local.microsecond // 1000
    return local.strftime("%d/%m/%Y %H:%M:%S.") + f"{ms:03d}"


def _status_label(code: str) -> str:
    if not code:
        return "—"
    return _STATUS_LABELS.get(code, code)


class NfIssueEventInline(admin.TabularInline):
    model = NfIssueEvent
    extra = 0
    can_delete = False
    show_change_link = False
    readonly_fields = (
        "from_status_display",
        "to_status_display",
        "actor_display",
        "metadata",
        "occurred_at_precise",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Status de origem")
    def from_status_display(self, obj: NfIssueEvent) -> str:
        return _status_label(obj.from_status)

    @admin.display(description="Status de destino")
    def to_status_display(self, obj: NfIssueEvent) -> str:
        return _status_label(obj.to_status)

    @admin.display(description="Ator")
    def actor_display(self, obj: NfIssueEvent) -> str:
        return _ACTOR_LABELS.get(obj.actor, obj.actor or "—")

    @admin.display(description="Ocorrido em")
    def occurred_at_precise(self, obj: NfIssueEvent) -> str:
        return _format_occurred_at(obj.occurred_at)


class NfArtifactInline(admin.TabularInline):
    model = NfArtifact
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("kind", "download_link", "checksum_sha256", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Arquivo")
    def download_link(self, obj: NfArtifact) -> str:
        if not obj.pk:
            return "—"
        url = reverse("admin:issuance_nfartifact_download", args=[obj.pk])
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Baixar {}</a>',
            url,
            obj.get_kind_display(),
        )


class NfIssueAdminForm(forms.ModelForm):
    """Form de criação — dispara InvoiceEngine (create_nf_issue), não save cru."""

    fiscal_profile = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label="Perfil fiscal",
        help_text=(
            "Obrigatório e do mesmo tenant da emissão. "
            "Há perfis com nome igual em tenants diferentes — escolha o do tenant selecionado."
        ),
    )

    class Meta:
        model = NfIssue
        fields = (
            "tenant",
            "idempotency_key",
            "provider",
            "customer",
            "service",
            "fiscal_profile",
            "ibge_code",
            "competence_date",
            "amount_cents",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.fiscal.models import FiscalProfile

        self.fields["fiscal_profile"].queryset = FiscalProfile.objects.select_related(
            "tenant"
        ).all()
        self.fields["fiscal_profile"].required = True
        self.fields["fiscal_profile"].label_from_instance = (
            lambda obj: f"{obj.name} ({obj.tenant.slug})"
        )
        for name in (
            "tenant",
            "idempotency_key",
            "provider",
            "customer",
            "service",
            "ibge_code",
            "competence_date",
            "amount_cents",
        ):
            self.fields[name].required = True

    def clean_amount_cents(self):
        value = self.cleaned_data["amount_cents"]
        if value is None or value <= 0:
            raise forms.ValidationError("O valor em centavos deve ser maior que zero.")
        return value

    def clean_fiscal_profile(self):
        profile = self.cleaned_data.get("fiscal_profile")
        if profile is None:
            raise forms.ValidationError("Selecione o perfil fiscal antes de salvar.")
        return profile

    def clean(self):
        cleaned = super().clean()
        tenant = cleaned.get("tenant")
        if not tenant:
            return cleaned
        for field in ("provider", "customer", "service", "fiscal_profile"):
            obj = cleaned.get(field)
            if obj is not None and obj.tenant_id != tenant.id:
                self.add_error(
                    field,
                    (
                        f"Deve pertencer ao tenant '{tenant.slug}'. "
                        f"O item selecionado é do tenant '{obj.tenant.slug}'."
                    ),
                )
        return cleaned


@admin.register(NfIssue)
class NfIssueAdmin(admin.ModelAdmin):
    form = NfIssueAdminForm
    list_display = (
        "idempotency_key",
        "status_badge",
        "tenant",
        "provider",
        "amount_cents",
        "ibge_code",
        "competence_date",
        "focus_ref",
        "created_at",
    )
    list_filter = ("status", "ibge_code", "tenant")
    search_fields = ("idempotency_key", "focus_ref", "rejection_code", "id")
    readonly_fields = (
        "status",
        "resolved_rule",
        "resolved_params",
        "internal_payload",
        "focus_status_raw",
        "focus_ref",
        "payload_hash",
        "correlation_id",
        "rejection_code",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("tenant", "provider", "customer", "service", "fiscal_profile")
    inlines = [NfArtifactInline, NfIssueEventInline]
    actions = (
        "action_poll_status",
        "action_cancel_authorized",
        "action_reprocess_rejected",
        "action_ensure_artifacts",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Emissão (QA)",
            {
                "fields": (
                    "tenant",
                    "idempotency_key",
                    "provider",
                    "customer",
                    "service",
                    "fiscal_profile",
                    "ibge_code",
                    "competence_date",
                    "amount_cents",
                )
            },
        ),
        (
            "Status / Focus (somente leitura)",
            {
                "fields": (
                    "status",
                    "focus_ref",
                    "rejection_code",
                    "correlation_id",
                    "resolved_rule",
                    "resolved_params",
                    "internal_payload",
                    "focus_status_raw",
                    "payload_hash",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Status")
    def status_badge(self, obj: NfIssue):
        colors = {
            NfIssue.Status.AUTHORIZED: "#0a7a2f",
            NfIssue.Status.REJECTED: "#a11",
            NfIssue.Status.CANCELLED: "#666",
            NfIssue.Status.FAILED: "#a11",
            NfIssue.Status.POLLING: "#a60",
            NfIssue.Status.QUEUED: "#06c",
        }
        color = colors.get(obj.status, "#333")
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            color,
            obj.get_status_display(),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self.readonly_fields

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (
                    "Nova emissão (QA)",
                    {
                        "description": (
                            "Ao salvar, o Hub resolve o imposto, enfileira e envia ao "
                            "provedor Focus (stub ou HTTP conforme .env)."
                        ),
                        "fields": (
                            "tenant",
                            "idempotency_key",
                            "provider",
                            "customer",
                            "service",
                            "fiscal_profile",
                            "ibge_code",
                            "competence_date",
                            "amount_cents",
                        ),
                    },
                ),
            )
        return self.fieldsets

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def save_model(self, request, obj, form, change):
        if change:
            messages.info(
                request,
                "Campos de emissão são somente leitura. Use as ações Cancelar / Reprocessar / Consultar status.",
            )
            return
        try:
            created = create_nf_issue(
                tenant=form.cleaned_data["tenant"],
                idempotency_key=form.cleaned_data["idempotency_key"],
                provider=form.cleaned_data["provider"],
                customer=form.cleaned_data["customer"],
                service=form.cleaned_data["service"],
                fiscal_profile=form.cleaned_data["fiscal_profile"],
                ibge_code=form.cleaned_data["ibge_code"],
                competence_date=form.cleaned_data["competence_date"],
                amount_cents=form.cleaned_data["amount_cents"],
            )
        except FiscalProfileRequiredError as exc:
            messages.error(request, str(exc))
            raise
        except Exception as exc:  # noqa: BLE001 — admin UX
            messages.error(request, f"Falha na emissão: {exc}")
            raise
        obj.pk = created.pk
        obj.id = created.id
        for field in obj._meta.concrete_fields:
            setattr(obj, field.attname, getattr(created, field.attname))
        messages.success(
            request,
            f"Emissão criada: status={created.status}, focus_ref={created.focus_ref or '-'}",
        )

    @admin.action(description="Consultar status no provedor")
    def action_poll_status(self, request, queryset):
        ok = 0
        for issue in queryset:
            try:
                poll_nf_issue_status(issue)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f"{issue.idempotency_key}: {exc}")
        messages.success(request, f"Consulta executada em {ok} nota(s).")

    @admin.action(description="Cancelar no Focus (autorizadas)")
    def action_cancel_authorized(self, request, queryset):
        ok = 0
        for issue in queryset:
            try:
                cancel_nf_issue(issue, justificativa=QA_CANCEL_JUSTIFICATIVA)
                ok += 1
            except (
                InvalidTransitionError,
                CancelJustificationError,
                FocusCancelFailedError,
            ) as exc:
                messages.error(request, f"{issue.idempotency_key}: {exc}")
        if ok:
            messages.success(request, f"{ok} nota(s) cancelada(s).")

    @admin.action(description="Reprocessar (rejeitadas/falhas)")
    def action_reprocess_rejected(self, request, queryset):
        ok = 0
        for issue in queryset:
            try:
                reprocess_nf_issue(issue)
                ok += 1
            except InvalidTransitionError as exc:
                messages.error(request, f"{issue.idempotency_key}: {exc}")
        if ok:
            messages.success(request, f"{ok} nota(s) reprocessada(s).")

    @admin.action(description="Garantir artefatos PDF/XML (autorizadas)")
    def action_ensure_artifacts(self, request, queryset):
        ok = 0
        for issue in queryset.filter(status=NfIssue.Status.AUTHORIZED):
            ensure_authorized_artifacts(issue)
            if issue.artifacts.exists():
                ok += 1
        if ok:
            messages.success(
                request,
                f"Artefatos conferidos em {ok} emissão(ões) autorizada(s).",
            )
        else:
            messages.warning(
                request,
                "Nenhuma emissão autorizada selecionada ou sem arquivo Focus.",
            )


@admin.register(NfIssueEvent)
class NfIssueEventAdmin(admin.ModelAdmin):
    list_display = (
        "nf_issue",
        "from_status_display",
        "to_status_display",
        "actor_display",
        "occurred_at_precise",
        "tenant",
    )
    list_filter = ("to_status", "actor")
    search_fields = ("nf_issue__idempotency_key",)
    readonly_fields = (
        "tenant",
        "nf_issue",
        "from_status_display",
        "to_status_display",
        "actor_display",
        "metadata",
        "occurred_at_precise",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Status de origem", ordering="from_status")
    def from_status_display(self, obj: NfIssueEvent) -> str:
        return _status_label(obj.from_status)

    @admin.display(description="Status de destino", ordering="to_status")
    def to_status_display(self, obj: NfIssueEvent) -> str:
        return _status_label(obj.to_status)

    @admin.display(description="Ator", ordering="actor")
    def actor_display(self, obj: NfIssueEvent) -> str:
        return _ACTOR_LABELS.get(obj.actor, obj.actor or "—")

    @admin.display(description="Ocorrido em", ordering="occurred_at")
    def occurred_at_precise(self, obj: NfIssueEvent) -> str:
        return _format_occurred_at(obj.occurred_at)


@admin.register(FiscalRuleSnapshot)
class FiscalRuleSnapshotAdmin(admin.ModelAdmin):
    list_display = ("nf_issue", "catalog_version", "source_rule_id", "tenant")
    search_fields = ("nf_issue__idempotency_key",)
    readonly_fields = ("tenant", "nf_issue", "source_rule_id", "catalog_version", "snapshot")


@admin.register(NfArtifact)
class NfArtifactAdmin(admin.ModelAdmin):
    list_display = (
        "nf_issue",
        "downloads",
        "tenant",
        "created_at",
    )
    list_filter = ("tenant",)
    search_fields = ("nf_issue__idempotency_key",)
    autocomplete_fields = ("tenant", "nf_issue", "stored_file")
    readonly_fields = (
        "tenant",
        "nf_issue",
        "kind",
        "stored_file",
        "download_link",
        "checksum_sha256",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        from django.db.models import Prefetch

        # Uma linha por emissão: PDF + XML juntos na coluna Downloads.
        return (
            super()
            .get_queryset(request)
            .select_related("nf_issue", "tenant")
            .prefetch_related(
                Prefetch(
                    "nf_issue__artifacts",
                    queryset=NfArtifact.objects.only("id", "kind", "nf_issue_id"),
                )
            )
            .order_by("nf_issue_id", "kind")
            .distinct("nf_issue_id")
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<uuid:object_id>/download/",
                self.admin_site.admin_view(self.download_view),
                name="issuance_nfartifact_download",
            ),
        ]
        return custom + urls

    def download_view(self, request, object_id):
        from io import BytesIO

        artifact = (
            NfArtifact.objects.select_related("stored_file", "nf_issue")
            .filter(pk=object_id)
            .first()
        )
        if artifact is None or artifact.stored_file_id is None:
            raise Http404("Artefato não encontrado")
        stored = artifact.stored_file
        try:
            data = get_storage().get(key=stored.object_key)
        except StorageError as exc:
            raise Http404(str(exc)) from exc
        ext = "pdf" if artifact.kind == NfArtifact.Kind.PDF else "xml"
        filename = f"{artifact.nf_issue.idempotency_key}-{artifact.kind}.{ext}"
        content_type = stored.content_type or (
            "application/pdf" if ext == "pdf" else "application/xml"
        )
        return FileResponse(
            BytesIO(data),
            as_attachment=True,
            filename=filename,
            content_type=content_type,
        )

    @admin.display(description="Downloads")
    def downloads(self, obj: NfArtifact) -> str:
        from django.utils.safestring import mark_safe

        by_kind = {a.kind: a for a in obj.nf_issue.artifacts.all()}
        parts = []
        for kind, label in (
            (NfArtifact.Kind.PDF, "PDF"),
            (NfArtifact.Kind.XML, "XML"),
        ):
            art = by_kind.get(kind)
            if art:
                url = reverse("admin:issuance_nfartifact_download", args=[art.pk])
                parts.append(
                    format_html(
                        '<a class="button" href="{}" target="_blank" rel="noopener"'
                        ' style="margin-right:8px">Baixar {}</a>',
                        url,
                        label,
                    )
                )
            else:
                parts.append(
                    format_html(
                        '<span style="margin-right:8px;opacity:.55">{} —</span>',
                        label,
                    )
                )
        return mark_safe("".join(parts)) if parts else "—"

    @admin.display(description="Arquivo")
    def download_link(self, obj: NfArtifact) -> str:
        """Detalhe do registro: mesmo padrão (PDF + XML na mesma linha)."""
        return self.downloads(obj)
