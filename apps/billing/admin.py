from django.contrib import admin
from django.utils.html import format_html

from apps.billing.models import Charge, PaymentEvent, PaymentProviderAudit, WebhookInbox
from shared.money import format_brl_from_cents


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    """
    Admin interno (ops/QA) — fieldsets alinhados ao layout Inter / produto React.
    Escopo PO: só reorganização visual. Emissão real continua via API create_charge.
    """

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
        "amount_brl",
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
        "schedule_group_id",
        "layout_hint",
    )
    actions = ("cancelar_cobrancas", "sincronizar_gateway")

    fieldsets = (
        (
            "1 · Tipo de emissão",
            {
                "description": (
                    "Como no Inter PJ: pagamento único, parcelado ou recorrente. "
                    "Admin = cadastro interno; emissão no banco via API POST /charges/."
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
                    "Valor em centavos (ex.: R$ 6,00 = 600). Inter mín. R$ 2,50. "
                    "Parcelado: valor total. Recorrente: valor de cada ocorrência."
                ),
                "fields": ("amount_cents", "amount_brl", "due_date"),
            },
        ),
        (
            "4 · Após o vencimento",
            {
                "description": (
                    "Espelho das predefinições (numDiasAgenda 0–60, multa %, juros % a.m.). "
                    "Na API esses valores vêm de GET/PUT /billing/presets."
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
                    "idempotency_key",
                    "status",
                    "billing_type",
                    "nf_issue",
                    "gateway_ref",
                    "digitable_line",
                    "barcode",
                    "pix_copy_paste",
                    "payment_url",
                    "boleto_pdf_url",
                    "gateway_payload",
                    "correlation_id",
                ),
            },
        ),
    )

    @admin.display(description="Valor", ordering="amount_cents")
    def amount_brl(self, obj: Charge) -> str:
        if not obj or obj.amount_cents is None:
            return "—"
        return format_brl_from_cents(obj.amount_cents)

    @admin.display(description="Orientação do layout")
    def layout_hint(self, obj: Charge) -> str:
        return format_html(
            "<span style='color:#555'>"
            "Blocos 1–6 seguem o wireframe Inter/Hub (ops/QA). "
            "Produto final = React. Status e PIX só após emitir/sincronizar."
            "</span>"
        )

    @admin.action(description="Cancelar cobranças selecionadas (gateway)")
    def cancelar_cobrancas(self, request, queryset):
        from apps.billing.exceptions import (
            GatewayRegistrationError,
            IncompatiblePaymentError,
            InvalidChargeInputError,
        )
        from apps.billing.services import cancel_charge

        ok = 0
        errors = []
        for charge in queryset:
            try:
                cancel_charge(charge, motivo_cancelamento="ACERTOS")
                ok += 1
            except (
                IncompatiblePaymentError,
                GatewayRegistrationError,
                InvalidChargeInputError,
            ) as exc:
                errors.append(f"{charge.id}: {exc}")
        if ok:
            self.message_user(request, f"{ok} cobrança(s) cancelada(s).")
        for err in errors[:10]:
            self.message_user(request, err, level="ERROR")

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
            self.message_user(request, err, level="ERROR")


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
    list_filter = ("provider", "status", "signature_valid")
    search_fields = ("idempotency_key", "payload_hash")
    readonly_fields = ("payload_hash", "processed_at")


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("charge", "amount_brl", "paid_at", "gateway_ref", "tenant")
    list_filter = ("paid_at",)
    search_fields = ("gateway_ref",)
    readonly_fields = ("amount_brl", "created_at")

    @admin.display(description="Valor", ordering="amount_cents")
    def amount_brl(self, obj: PaymentEvent) -> str:
        return format_brl_from_cents(obj.amount_cents)


@admin.register(PaymentProviderAudit)
class PaymentProviderAuditAdmin(admin.ModelAdmin):
    list_display = ("provider", "action", "actor_user", "tenant", "created_at")
    list_filter = ("provider", "action")
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
