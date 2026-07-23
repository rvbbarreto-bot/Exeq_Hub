from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.http import FileResponse, Http404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from uuid import uuid4

from apps.billing.admin_form_fields import (
    NumericTextInput,
    parse_br_decimal,
    parse_int_digits,
    parse_valor_reais_to_cents,
)
from apps.billing.amount_rules import (
    CHARGE_MIN_AMOUNT_BRL,
    CHARGE_MIN_AMOUNT_CENTS,
    validate_charge_amount_cents,
)
from apps.billing.cancel_views import MOTIVO_LABELS
from apps.billing.due_date_rules import min_due_date, validate_due_date
from apps.billing.models import Charge, PaymentEvent, PaymentProviderAudit, WebhookInbox
from integrations.payments.inter_cancel import (
    DEFAULT_INTER_CANCEL_MOTIVO,
    INTER_CANCEL_MOTIVOS,
)
from shared.money import format_brl_from_cents
from shared.storage import StorageError, get_storage


def _new_admin_idempotency_key() -> str:
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    return f"admin-{stamp}-{uuid4().hex[:8]}"


class ChargeAdminForm(forms.ModelForm):
    valor_reais = forms.CharField(
        label="Valor",
        help_text=(
            f"Informe em reais (ex.: 6,00). Mínimo {CHARGE_MIN_AMOUNT_BRL}."
        ),
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "inputmode": "decimal",
                "autocomplete": "off",
                "placeholder": "0,00",
                "style": "width:12em;",
            }
        ),
    )
    # CharField evita type=number (browser aceita "e") e permite "2,50".
    num_dias_agenda = forms.CharField(
        label="Dias após vencimento",
        required=False,
        widget=NumericTextInput(),
    )
    multa_percent = forms.CharField(
        label="Multa %",
        required=False,
        widget=NumericTextInput(decimal=True),
    )
    mora_percent_am = forms.CharField(
        label="Juros % a.m.",
        required=False,
        widget=NumericTextInput(decimal=True),
    )

    class Meta:
        model = Charge
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Armazenamento continua em centavos; UI usa Valor em R$.
        if "amount_cents" in self.fields:
            del self.fields["amount_cents"]

        if self.instance and self.instance.pk and self.instance.amount_cents:
            self.fields["valor_reais"].initial = (
                format_brl_from_cents(self.instance.amount_cents).replace("R$ ", "")
            )

        if self.instance and self.instance.pk:
            if self.instance.num_dias_agenda is not None:
                self.fields["num_dias_agenda"].initial = str(self.instance.num_dias_agenda)
            if self.instance.multa_percent is not None:
                self.fields["multa_percent"].initial = (
                    f"{self.instance.multa_percent}".replace(".", ",")
                )
            if self.instance.mora_percent_am is not None:
                self.fields["mora_percent_am"].initial = (
                    f"{self.instance.mora_percent_am}".replace(".", ",")
                )

        if "due_date" in self.fields:
            minimum = min_due_date()
            self.fields["due_date"].widget = forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "type": "date",
                    "min": minimum.isoformat(),
                },
            )
            self.fields["due_date"].input_formats = [
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%d-%m-%Y",
            ]
            self.fields["due_date"].help_text = (
                "Não permite datas anteriores ao dia atual. "
                "Após 16:00 (horário local), o vencimento mínimo é o dia seguinte."
            )

        if "idempotency_key" in self.fields:
            field = self.fields["idempotency_key"]
            field.help_text = (
                "Gerada automaticamente pelo sistema. Evita cobrança duplicada "
                "em reenvios. Não é editável."
            )
            field.widget.attrs["readonly"] = True
            field.widget.attrs["style"] = "background:#f5f5f5;color:#333;width:28em;"
            if self.instance and self.instance.pk and self.instance.idempotency_key:
                field.initial = self.instance.idempotency_key
            elif not field.initial and not (self.data or {}).get("idempotency_key"):
                field.initial = _new_admin_idempotency_key()

        # Campos de sistema: no Admin ficam readonly; no form isolado não devem bloquear.
        for name in (
            "status",
            "correlation_id",
            "gateway_ref",
            "gateway_payload",
            "message_lines",
            "digitable_line",
            "barcode",
            "pix_copy_paste",
            "payment_url",
            "boleto_pdf_url",
            "schedule_group_id",
        ):
            if name in self.fields:
                self.fields[name].required = False

    def clean_valor_reais(self):
        cents = parse_valor_reais_to_cents(self.cleaned_data.get("valor_reais") or "")
        try:
            validate_charge_amount_cents(cents)
        except ValueError as exc:
            raise forms.ValidationError(str(exc), code="min_amount") from exc
        self._amount_cents = cents
        return self.cleaned_data.get("valor_reais")

    def clean_due_date(self):
        value = self.cleaned_data.get("due_date")
        if value is None:
            return value
        try:
            validate_due_date(value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc), code="due_date") from exc
        return value

    def clean_num_dias_agenda(self):
        return parse_int_digits(self.cleaned_data.get("num_dias_agenda"))

    def clean_multa_percent(self):
        return parse_br_decimal(self.cleaned_data.get("multa_percent"))

    def clean_mora_percent_am(self):
        return parse_br_decimal(self.cleaned_data.get("mora_percent_am"))

    def clean_idempotency_key(self):
        if self.instance and self.instance.pk and self.instance.idempotency_key:
            return self.instance.idempotency_key
        value = (self.cleaned_data.get("idempotency_key") or "").strip()
        return value or _new_admin_idempotency_key()

    def clean(self):
        cleaned = super().clean()
        cents = getattr(self, "_amount_cents", None)
        if cents is not None:
            cleaned["amount_cents"] = cents
            self.instance.amount_cents = cents
        return cleaned


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    """
    Admin interno (ops/QA) — fieldsets Inter + emissão real via create_charge / Inter.
    """

    form = ChargeAdminForm
    list_display = (
        "idempotency_key",
        "seu_numero",
        "charge_kind",
        "status",
        "amount_brl",
        "gateway_ref",
        "tenant",
    )
    list_filter = ("status", "billing_type", "charge_kind")
    search_fields = ("idempotency_key", "gateway_ref", "digitable_line", "seu_numero")
    autocomplete_fields = ("customer", "nf_issue")
    readonly_fields = (
        "status",
        "gateway_ref",
        "correlation_id",
        "gateway_payload",
        "message_lines",
        "digitable_line",
        "barcode",
        "pix_copy_paste",
        "payment_url",
        "boleto_pdf_url",
        "pdf_download_link",
        "schedule_group_id",
        "layout_hint",
    )
    actions = (
        "emitir_no_gateway",
        "cancelar_cobrancas",
        "sincronizar_gateway",
    )

    fieldsets = (
        (
            "Controle do sistema",
            {
                "description": (
                    "Chave de idempotência gerada automaticamente — visível, sem edição. "
                    "Ao salvar uma nova cobrança, o Hub emite o boleto no provedor (Inter)."
                ),
                "fields": ("idempotency_key",),
            },
        ),
        (
            "1 · Tipo de emissão",
            {
                "description": (
                    "Como no Inter PJ: pagamento único, parcelado ou recorrente. "
                    "Salvar dispara create_charge → API do banco."
                ),
                "fields": ("charge_kind", "layout_hint"),
            },
        ),
        (
            "2 · Pagador",
            {
                "description": "Tomador que aparece no boleto (pagador Inter).",
                "fields": ("customer",),
            },
        ),
        (
            "3 · Valor e vencimento",
            {
                "description": (
                    f"Valor em reais (ex.: 6,00). Mínimo {CHARGE_MIN_AMOUNT_BRL}. "
                    "Parcelado: valor total. Recorrente: valor de cada ocorrência. "
                    "Após 16:00 (horário local), vencimento mínimo = dia seguinte."
                ),
                "fields": ("valor_reais", "due_date"),
            },
        ),
        (
            "4 · Após o vencimento",
            {
                "description": (
                    "Espelho das predefinições (numDiasAgenda 0–60, multa %, juros % a.m.). "
                    "Na API esses valores vêm de GET/PUT /billing/presets. "
                    "Somente números."
                ),
                "fields": ("num_dias_agenda", "multa_percent", "mora_percent_am"),
            },
        ),
        (
            "5 · Identificação e mensagem no boleto",
            {
                "description": (
                    "Código de controle = seuNumero Inter (máx. 15). "
                    "Descrição livre; linhas do boleto (5×78) são preenchidas na emissão API."
                ),
                "fields": ("seu_numero", "description", "message_lines"),
            },
        ),
        (
            "6 · Agenda (parcelada / recorrente)",
            {
                "description": (
                    "Preencher quando o tipo não for pagamento único. "
                    "Parcela atual / total; grupo liga o carnê."
                ),
                "fields": (
                    "installment_number",
                    "installment_count",
                    "schedule_group_id",
                ),
            },
        ),
        (
            "Sistema e artefatos (somente leitura)",
            {
                "classes": ("collapse",),
                "description": "Gerados pelo gateway — não editar manualmente.",
                "fields": (
                    "tenant",
                    "status",
                    "billing_type",
                    "nf_issue",
                    "gateway_ref",
                    "digitable_line",
                    "barcode",
                    "pix_copy_paste",
                    "payment_url",
                    "boleto_pdf_url",
                    "pdf_download_link",
                    "gateway_payload",
                    "correlation_id",
                ),
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<uuid:object_id>/pdf/",
                self.admin_site.admin_view(self.download_pdf_view),
                name="billing_charge_pdf",
            ),
        ]
        return custom + urls

    def download_pdf_view(self, request, object_id):
        from io import BytesIO

        from apps.billing.services import ensure_charge_pdf

        charge = Charge.objects.filter(pk=object_id).select_related("pdf_file").first()
        if charge is None:
            raise Http404("Cobrança não encontrada")
        try:
            ensure_charge_pdf(charge)
        except Exception as exc:
            raise Http404(str(exc)) from exc
        charge.refresh_from_db()
        if not charge.pdf_file_id:
            raise Http404("PDF indisponível")
        stored = charge.pdf_file
        try:
            data = get_storage().get(key=stored.object_key)
        except StorageError as exc:
            raise Http404(str(exc)) from exc
        filename = f"boleto-{charge.seu_numero or charge.id}.pdf"
        return FileResponse(
            BytesIO(data),
            as_attachment=True,
            filename=filename,
            content_type=stored.content_type or "application/pdf",
        )

    @admin.display(description="PDF boleto")
    def pdf_download_link(self, obj: Charge):
        if not obj.pk:
            return "—"
        url = reverse("admin:billing_charge_pdf", args=[obj.pk])
        label = "Baixar PDF" if obj.pdf_file_id else "Buscar e baixar PDF"
        return format_html('<a href="{}">{}</a>', url, label)

    def get_changeform_initial_data(self, request):
        data = super().get_changeform_initial_data(request)
        data["idempotency_key"] = _new_admin_idempotency_key()
        data["due_date"] = min_due_date()
        return data

    def save_model(self, request, obj, form, change):
        from apps.billing.exceptions import (
            GatewayRegistrationError,
            InvalidChargeInputError,
        )
        from apps.billing.services import create_charge, emit_pending_charge

        if change:
            original = Charge.objects.filter(pk=obj.pk).first()
            if original and original.idempotency_key:
                obj.idempotency_key = original.idempotency_key
            if original and original.gateway_ref:
                messages.info(
                    request,
                    "Cobrança já emitida no gateway. Use Sincronizar / Cancelar. "
                    "Campos de emissão não alteram o boleto no banco.",
                )
                return
            # Pending/failed sem gateway: salvar dados do form e emitir
            if "amount_cents" in form.cleaned_data:
                obj.amount_cents = form.cleaned_data["amount_cents"]
            super().save_model(request, obj, form, change)
            try:
                emitted = emit_pending_charge(obj)
            except (InvalidChargeInputError, GatewayRegistrationError) as exc:
                messages.error(request, f"Falha na emissão: {exc}")
                raise
            obj.pk = emitted.pk
            for field in obj._meta.concrete_fields:
                setattr(obj, field.attname, getattr(emitted, field.attname))
            messages.success(
                request,
                f"Boleto emitido. status={emitted.status}, gateway_ref={emitted.gateway_ref or '-'}",
            )
            return

        if not (obj.idempotency_key or "").strip():
            obj.idempotency_key = _new_admin_idempotency_key()

        installments = None
        if obj.charge_kind == Charge.ChargeKind.INSTALLMENT:
            installments = obj.installment_count
        elif obj.charge_kind == Charge.ChargeKind.RECURRING and obj.installment_count:
            installments = obj.installment_count

        try:
            created = create_charge(
                tenant=form.cleaned_data["tenant"],
                idempotency_key=obj.idempotency_key,
                customer=form.cleaned_data["customer"],
                amount_cents=form.cleaned_data["amount_cents"],
                due_date=form.cleaned_data["due_date"],
                description=form.cleaned_data.get("description") or "",
                seu_numero=(form.cleaned_data.get("seu_numero") or "").strip() or None,
                charge_kind=form.cleaned_data.get(
                    "charge_kind", Charge.ChargeKind.SIMPLE
                ),
                installment_count=installments,
                nf_issue=form.cleaned_data.get("nf_issue"),
            )
        except (InvalidChargeInputError, GatewayRegistrationError) as exc:
            messages.error(request, f"Falha na emissão: {exc}")
            raise
        except Exception as exc:  # noqa: BLE001 — admin UX
            messages.error(request, f"Falha na emissão: {exc}")
            raise

        if isinstance(created, list):
            messages.success(
                request,
                f"{len(created)} cobrança(s) emitida(s). "
                f"Primeira ref={created[0].gateway_ref or '-'}",
            )
            created = created[0]
        else:
            messages.success(
                request,
                f"Boleto emitido. status={created.status}, "
                f"gateway_ref={created.gateway_ref or '-'}",
            )

        obj.pk = created.pk
        obj.id = created.id
        for field in obj._meta.concrete_fields:
            setattr(obj, field.attname, getattr(created, field.attname))

    @admin.display(description="Valor", ordering="amount_cents")
    def amount_brl(self, obj: Charge) -> str:
        if not obj or obj.amount_cents is None:
            return "—"
        return format_brl_from_cents(obj.amount_cents)

    @admin.display(description="Orientação do layout")
    def layout_hint(self, obj: Charge) -> str:
        return format_html(
            "<span style='color:#555'>"
            "Salvar emite no Inter (create_charge). "
            "Pendentes antigos: ação “Emitir cobrança no gateway”."
            "</span>"
        )

    @admin.action(description="Emitir cobrança no gateway (pendentes sem ref)")
    def emitir_no_gateway(self, request, queryset):
        from apps.billing.exceptions import (
            GatewayRegistrationError,
            InvalidChargeInputError,
        )
        from apps.billing.services import emit_pending_charge

        ok = 0
        errors = []
        for charge in queryset:
            if charge.gateway_ref:
                errors.append(f"{charge.idempotency_key}: já possui gateway_ref")
                continue
            try:
                emit_pending_charge(charge)
                ok += 1
            except (InvalidChargeInputError, GatewayRegistrationError) as exc:
                errors.append(f"{charge.idempotency_key}: {exc}")
        if ok:
            self.message_user(request, f"{ok} cobrança(s) emitida(s) no gateway.")
        for err in errors[:15]:
            self.message_user(request, err, level=messages.ERROR)

    @admin.action(description="Cancelar cobranças selecionadas (gateway)")
    def cancelar_cobrancas(self, request, queryset):
        from apps.billing.exceptions import (
            GatewayRegistrationError,
            IncompatiblePaymentError,
            InvalidChargeInputError,
        )
        from apps.billing.services import cancel_charge

        cancellable_statuses = {
            Charge.Status.PENDING,
            Charge.Status.REGISTERED,
            Charge.Status.OVERDUE,
        }
        eligible = list(
            queryset.filter(status__in=cancellable_statuses).select_related("tenant")
        )
        skipped = list(queryset.exclude(status__in=cancellable_statuses))

        if not eligible:
            self.message_user(
                request,
                "Nenhuma cobrança cancelável selecionada "
                "(pending / registered / overdue).",
                level=messages.ERROR,
            )
            return None

        if request.POST.get("apply") != "1":
            motivos = [
                {
                    "value": m,
                    "label": MOTIVO_LABELS.get(m, m),
                    "selected": m == DEFAULT_INTER_CANCEL_MOTIVO,
                }
                for m in sorted(INTER_CANCEL_MOTIVOS)
            ]
            return TemplateResponse(
                request,
                "admin/billing/charge/bulk_cancel.html",
                {
                    **self.admin_site.each_context(request),
                    "opts": self.model._meta,
                    "eligible": eligible,
                    "skipped": skipped,
                    "motivos": motivos,
                    "default_motivo": DEFAULT_INTER_CANCEL_MOTIVO,
                    "action_checkbox_name": ACTION_CHECKBOX_NAME,
                    "back_url": reverse("admin:billing_charge_changelist"),
                    "title": "Confirmar cancelamento no gateway",
                },
            )

        motivo = (request.POST.get("motivo_cancelamento") or "").strip().upper()
        if motivo not in INTER_CANCEL_MOTIVOS:
            self.message_user(
                request,
                f"Motivo inválido. Use: {', '.join(sorted(INTER_CANCEL_MOTIVOS))}",
                level=messages.ERROR,
            )
            return None

        ok = 0
        errors = []
        for charge in eligible:
            try:
                cancel_charge(charge, motivo_cancelamento=motivo)
                ok += 1
            except (
                IncompatiblePaymentError,
                GatewayRegistrationError,
                InvalidChargeInputError,
            ) as exc:
                errors.append(f"{charge.id}: {exc}")
        if ok:
            label = MOTIVO_LABELS.get(motivo, motivo)
            self.message_user(
                request,
                f"{ok} cobrança(s) cancelada(s) com motivo {label} ({motivo}).",
            )
        if skipped:
            self.message_user(
                request,
                f"{len(skipped)} cobrança(s) ignorada(s) por status incompatível.",
                level=messages.WARNING,
            )
        for err in errors[:10]:
            self.message_user(request, err, level=messages.ERROR)
        return None

    @admin.action(description="Sincronizar status/pagamento com o gateway")
    def sincronizar_gateway(self, request, queryset):
        from apps.billing.exceptions import ChargeNotFoundError, GatewayRegistrationError
        from apps.billing.services import sync_charge_from_gateway

        ok = 0
        errors = []
        for charge in queryset:
            try:
                sync_charge_from_gateway(charge)
                ok += 1
            except (ChargeNotFoundError, GatewayRegistrationError) as exc:
                errors.append(f"{charge.id}: {exc}")
        if ok:
            self.message_user(request, f"{ok} cobrança(s) sincronizada(s).")
        for err in errors[:10]:
            self.message_user(request, err, level=messages.ERROR)


@admin.register(WebhookInbox)
class WebhookInboxAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "idempotency_key",
        "status",
        "signature_valid",
        "tenant",
        "processed_at",
    )
    list_filter = ("provider", "status", "signature_valid", "tenant")
    search_fields = ("idempotency_key", "payload_hash", "error_message")
    readonly_fields = (
        "payload_hash",
        "processed_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "tenant",
                    "provider",
                    "idempotency_key",
                    "status",
                ),
            },
        ),
        (
            "Assinatura",
            {"fields": ("signature", "signature_valid")},
        ),
        (
            "Payload",
            {"fields": ("raw_payload", "payload_hash")},
        ),
        (
            "Processamento",
            {
                "fields": (
                    "error_message",
                    "processed_at",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = (
        "charge",
        "amount_brl",
        "paid_at",
        "gateway_ref",
        "tenant",
        "created_at",
    )
    list_filter = ("paid_at", "tenant")
    search_fields = ("gateway_ref", "charge__idempotency_key")
    readonly_fields = (
        "amount_brl",
        "created_at",
        "tenant",
        "charge",
        "webhook_inbox",
        "paid_at",
        "gateway_ref",
        "metadata",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "tenant",
                    "charge",
                    "webhook_inbox",
                    "amount_brl",
                    "paid_at",
                    "gateway_ref",
                ),
            },
        ),
        (
            "Metadados",
            {"fields": ("metadata", "created_at")},
        ),
    )

    @admin.display(description="Valor", ordering="amount_cents")
    def amount_brl(self, obj: PaymentEvent) -> str:
        return format_brl_from_cents(obj.amount_cents)


@admin.register(PaymentProviderAudit)
class PaymentProviderAuditAdmin(admin.ModelAdmin):
    list_display = ("provider", "action", "actor_user", "tenant", "created_at")
    list_filter = ("provider", "action", "tenant")
    search_fields = ("provider", "action")
    readonly_fields = (
        "tenant",
        "provider",
        "action",
        "actor_user",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
