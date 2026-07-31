from django.contrib import admin

from apps.scheduling.models import (
    Appointment,
    AppointmentFinancial,
    BusinessHours,
    CalendarBlock,
    CommissionEntry,
    CommissionRule,
    CustomerRestriction,
    Professional,
    ProfessionalService,
    RecurringTimeOff,
    Service,
    TimeOff,
)
from shared.money import format_brl_from_cents


class SchedulingAdminMixin:
    """Rótulos de UI do Agendador: Tenant → Empresa; centavos → R$."""

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "tenant":
            kwargs["label"] = "Empresa"
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)
        if "tenant" in form.base_fields:
            form.base_fields["tenant"].label = "Empresa"
        return form

    @admin.display(description="Empresa", ordering="tenant")
    def empresa(self, obj):
        return obj.tenant


def _cents_display(description: str, attr: str):
    @admin.display(description=description, ordering=attr)
    def _display(self, obj):
        if obj is None:
            return "—"
        value = getattr(obj, attr, None)
        return format_brl_from_cents(value)

    _display.__name__ = f"{attr}_brl"
    return _display


@admin.register(Professional)
class ProfessionalAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = ("name", "provider", "is_active", "timezone", "empresa")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(Service)
class ServiceAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "duration_minutes",
        "price_brl",
        "is_active",
        "empresa",
    )
    search_fields = ("name",)
    list_filter = ("is_active",)
    price_brl = _cents_display("Preço", "price_cents")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)
        if "price_cents" in form.base_fields:
            form.base_fields["price_cents"].label = "Preço (centavos)"
            form.base_fields["price_cents"].help_text = (
                "Informe em centavos (ex.: 5000 = R$ 50,00). "
                "Na listagem o valor aparece formatado em R$."
            )
        return form


@admin.register(ProfessionalService)
class ProfessionalServiceAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = ("professional", "service", "empresa")
    search_fields = ("professional__name", "service__name")


@admin.register(BusinessHours)
class BusinessHoursAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = ("professional", "weekday", "starts_at", "ends_at", "empresa")


@admin.register(TimeOff)
class TimeOffAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = ("professional", "starts_at", "ends_at", "reason", "empresa")
    search_fields = ("reason", "professional__name")


@admin.register(RecurringTimeOff)
class RecurringTimeOffAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = ("professional", "weekday", "starts_at", "ends_at", "empresa")


@admin.register(CalendarBlock)
class CalendarBlockAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = (
        "professional",
        "starts_at",
        "ends_at",
        "reason",
        "created_by",
        "empresa",
    )
    search_fields = ("reason", "professional__name")


@admin.register(Appointment)
class AppointmentAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = (
        "customer",
        "professional",
        "service",
        "starts_at",
        "price_brl",
        "status",
        "source",
        "empresa",
    )
    list_filter = ("status", "source")
    search_fields = ("customer__name", "notes")
    price_brl = _cents_display("Preço", "price_cents")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)
        if "price_cents" in form.base_fields:
            form.base_fields["price_cents"].label = "Preço (centavos)"
            form.base_fields["price_cents"].help_text = (
                "Centavos (ex.: 5000 = R$ 50,00). Listagem em R$."
            )
        return form


@admin.register(CustomerRestriction)
class CustomerRestrictionAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = (
        "customer",
        "requires_deposit",
        "manual_booking_only",
        "empresa",
    )


@admin.register(CommissionRule)
class CommissionRuleAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = (
        "rule_kind",
        "priority",
        "is_active",
        "professional",
        "service",
        "percent_display",
        "fixed_brl",
        "empresa",
    )
    list_filter = ("rule_kind", "is_active")
    fixed_brl = _cents_display("Valor fixo", "fixed_cents")

    @admin.display(description="Percentual", ordering="percent_basis_points")
    def percent_display(self, obj):
        if obj is None or obj.percent_basis_points is None:
            return "—"
        return f"{(obj.percent_basis_points / 100):.2f}%".replace(".", ",")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)
        if "fixed_cents" in form.base_fields:
            form.base_fields["fixed_cents"].label = "Valor fixo (centavos)"
            form.base_fields["fixed_cents"].help_text = (
                "Centavos (ex.: 1500 = R$ 15,00). Listagem em R$."
            )
        return form


@admin.register(AppointmentFinancial)
class AppointmentFinancialAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = (
        "appointment",
        "service_price_brl",
        "deposit_brl",
        "discount_brl",
        "balance_brl",
        "settled_at",
        "empresa",
    )
    readonly_fields = ("balance_brl_detail",)
    service_price_brl = _cents_display("Preço serviço", "service_price_cents")
    deposit_brl = _cents_display("Sinal", "deposit_paid_cents")
    discount_brl = _cents_display("Desconto", "discount_cents")

    @admin.display(description="Saldo")
    def balance_brl(self, obj):
        if obj is None:
            return "—"
        return format_brl_from_cents(obj.balance_due_cents)

    @admin.display(description="Saldo devido")
    def balance_brl_detail(self, obj):
        return self.balance_brl(obj)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)
        labels = {
            "service_price_cents": "Preço do serviço (centavos)",
            "deposit_paid_cents": "Sinal pago (centavos)",
            "discount_cents": "Desconto (centavos)",
        }
        for name, label in labels.items():
            if name in form.base_fields:
                form.base_fields[name].label = label
                form.base_fields[name].help_text = (
                    "Valor em centavos (ex.: 5000 = R$ 50,00). Listagem em R$."
                )
        return form

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if "balance_brl_detail" not in fields:
            fields.append("balance_brl_detail")
        return fields


@admin.register(CommissionEntry)
class CommissionEntryAdmin(SchedulingAdminMixin, admin.ModelAdmin):
    list_display = (
        "appointment",
        "professional",
        "base_brl",
        "commission_brl",
        "status",
        "empresa",
    )
    list_filter = ("status",)
    base_brl = _cents_display("Base", "base_amount_cents")
    commission_brl = _cents_display("Comissão", "commission_cents")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj=obj, change=change, **kwargs)
        for name, label in (
            ("base_amount_cents", "Base (centavos)"),
            ("commission_cents", "Comissão (centavos)"),
        ):
            if name in form.base_fields:
                form.base_fields[name].label = label
                form.base_fields[name].help_text = (
                    "Centavos (ex.: 4000 = R$ 40,00). Listagem em R$."
                )
        return form
