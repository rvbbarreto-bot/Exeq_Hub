from django.conf import settings
from django.db import models
from django.db.models import F, Q

from shared.tenancy import TenantOwnedModel


class Professional(TenantOwnedModel):
    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="professionals",
        verbose_name="Prestador",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduling_professionals",
        verbose_name="Usuário",
    )
    name = models.CharField(max_length=255, verbose_name="Nome")
    timezone = models.CharField(
        max_length=64,
        default="America/Sao_Paulo",
        verbose_name="Fuso horário",
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Profissional"
        verbose_name_plural = "Profissionais"
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "provider"]),
        ]

    def __str__(self) -> str:
        return self.name


class Service(TenantOwnedModel):
    catalog_item = models.ForeignKey(
        "master_data.ServiceCatalogItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduling_services",
        verbose_name="Item do catálogo fiscal",
    )
    name = models.CharField(max_length=255, verbose_name="Nome")
    duration_minutes = models.PositiveIntegerField(verbose_name="Duração (min)")
    price_cents = models.BigIntegerField(default=0, verbose_name="Preço")
    buffer_before_minutes = models.PositiveIntegerField(
        default=0, verbose_name="Buffer antes (min)"
    )
    buffer_after_minutes = models.PositiveIntegerField(
        default=0, verbose_name="Buffer depois (min)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Serviço (agenda)"
        verbose_name_plural = "Serviços (agenda)"
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=5) & Q(duration_minutes__lte=480),
                name="ck_scheduling_service_duration_range",
            ),
            models.CheckConstraint(
                condition=Q(price_cents__gte=0),
                name="ck_scheduling_service_price_nonneg",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name


class ProfessionalService(TenantOwnedModel):
    professional = models.ForeignKey(
        Professional,
        on_delete=models.CASCADE,
        related_name="professional_services",
        verbose_name="Profissional",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="professional_services",
        verbose_name="Serviço",
    )

    class Meta:
        verbose_name = "Profissional × serviço"
        verbose_name_plural = "Profissionais × serviços"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "professional", "service"],
                name="uq_scheduling_professional_service",
            )
        ]

    def __str__(self) -> str:
        return f"{self.professional} / {self.service}"


class BusinessHours(TenantOwnedModel):
    professional = models.ForeignKey(
        Professional,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="business_hours",
        verbose_name="Profissional",
    )
    weekday = models.PositiveSmallIntegerField(verbose_name="Dia da semana")
    starts_at = models.TimeField(verbose_name="Início")
    ends_at = models.TimeField(verbose_name="Fim")

    class Meta:
        verbose_name = "Horário comercial"
        verbose_name_plural = "Horários comerciais"
        constraints = [
            models.CheckConstraint(
                condition=Q(weekday__gte=0) & Q(weekday__lte=6),
                name="ck_scheduling_business_hours_weekday",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="ck_scheduling_business_hours_range",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "professional", "weekday"]),
        ]

    def __str__(self) -> str:
        who = self.professional.name if self.professional_id else "tenant"
        return f"{who} wd={self.weekday} {self.starts_at}-{self.ends_at}"


class TimeOff(TenantOwnedModel):
    professional = models.ForeignKey(
        Professional,
        on_delete=models.CASCADE,
        related_name="time_offs",
        verbose_name="Profissional",
    )
    starts_at = models.DateTimeField(verbose_name="Início")
    ends_at = models.DateTimeField(verbose_name="Fim")
    reason = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Motivo"
    )

    class Meta:
        verbose_name = "Folga"
        verbose_name_plural = "Folgas"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="ck_scheduling_time_off_range",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "professional", "starts_at", "ends_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.professional} {self.starts_at}→{self.ends_at}"


class RecurringTimeOff(TenantOwnedModel):
    professional = models.ForeignKey(
        Professional,
        on_delete=models.CASCADE,
        related_name="recurring_time_offs",
        verbose_name="Profissional",
    )
    weekday = models.PositiveSmallIntegerField(verbose_name="Dia da semana")
    starts_at = models.TimeField(verbose_name="Início")
    ends_at = models.TimeField(verbose_name="Fim")

    class Meta:
        verbose_name = "Folga recorrente"
        verbose_name_plural = "Folgas recorrentes"
        constraints = [
            models.CheckConstraint(
                condition=Q(weekday__gte=0) & Q(weekday__lte=6),
                name="ck_scheduling_recurring_time_off_weekday",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="ck_scheduling_recurring_time_off_range",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "professional", "weekday"]),
        ]

    def __str__(self) -> str:
        return f"{self.professional} wd={self.weekday} {self.starts_at}-{self.ends_at}"


class CalendarBlock(TenantOwnedModel):
    professional = models.ForeignKey(
        Professional,
        on_delete=models.CASCADE,
        related_name="calendar_blocks",
        verbose_name="Profissional",
    )
    starts_at = models.DateTimeField(verbose_name="Início")
    ends_at = models.DateTimeField(verbose_name="Fim")
    reason = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Motivo"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduling_calendar_blocks",
        verbose_name="Criado por",
    )

    class Meta:
        verbose_name = "Bloqueio de agenda"
        verbose_name_plural = "Bloqueios de agenda"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="ck_scheduling_calendar_block_range",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "professional", "starts_at", "ends_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.professional} block {self.starts_at}→{self.ends_at}"


class Appointment(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        CONFIRMED = "confirmed", "Confirmado"
        NO_SHOW_PENDING = "no_show_pending", "No-show pendente"
        NO_SHOW = "no_show", "No-show"
        CHECKED_IN = "checked_in", "Check-in"
        IN_PROGRESS = "in_progress", "Em andamento"
        COMPLETED = "completed", "Concluído"
        CANCELLED = "cancelled", "Cancelado"

    class Source(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        PORTAL = "portal", "Portal"
        WALK_IN = "walk_in", "Walk-in"
        ADMIN = "admin", "Admin"

    professional = models.ForeignKey(
        Professional,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Profissional",
    )
    customer = models.ForeignKey(
        "master_data.Customer",
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Cliente",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Serviço",
    )
    starts_at = models.DateTimeField(verbose_name="Início")
    ends_at = models.DateTimeField(verbose_name="Fim")
    price_cents = models.BigIntegerField(default=0, verbose_name="Preço")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.ADMIN,
        verbose_name="Origem",
    )
    explicit_confirmation = models.BooleanField(
        default=False, verbose_name="Confirmação explícita"
    )
    notes = models.TextField(blank=True, default="", verbose_name="Observações")
    idempotency_key = models.CharField(
        max_length=128, verbose_name="Chave de idempotência"
    )

    class Meta:
        verbose_name = "Agendamento"
        verbose_name_plural = "Agendamentos"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="ck_scheduling_appointment_range",
            ),
            models.CheckConstraint(
                condition=Q(price_cents__gte=0),
                name="ck_scheduling_appointment_price_nonneg",
            ),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_scheduling_appointment_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "professional", "starts_at"]),
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.customer} @ {self.starts_at} ({self.status})"


class CustomerRestriction(TenantOwnedModel):
    customer = models.OneToOneField(
        "master_data.Customer",
        on_delete=models.CASCADE,
        related_name="scheduling_restriction",
        verbose_name="Cliente",
    )
    requires_deposit = models.BooleanField(
        default=False, verbose_name="Exige sinal"
    )
    manual_booking_only = models.BooleanField(
        default=False, verbose_name="Somente agendamento manual"
    )

    class Meta:
        verbose_name = "Restrição de cliente"
        verbose_name_plural = "Restrições de cliente"

    def __str__(self) -> str:
        return f"restriction:{self.customer_id}"


class CommissionRule(TenantOwnedModel):
    class RuleKind(models.TextChoices):
        PERCENT = "percent", "Percentual"
        FIXED_CENTS = "fixed_cents", "Valor fixo"

    branch_id = models.UUIDField(
        null=True, blank=True, verbose_name="Unidade (UUID)"
    )
    professional = models.ForeignKey(
        Professional,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="commission_rules",
        verbose_name="Profissional",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="commission_rules",
        verbose_name="Serviço",
    )
    rule_kind = models.CharField(
        max_length=16,
        choices=RuleKind.choices,
        verbose_name="Tipo de regra",
    )
    percent_basis_points = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Percentual (bps)"
    )
    fixed_cents = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Valor fixo"
    )
    priority = models.IntegerField(default=0, verbose_name="Prioridade")
    is_active = models.BooleanField(default=True, verbose_name="Ativa")

    class Meta:
        verbose_name = "Regra de comissão"
        verbose_name_plural = "Regras de comissão"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        Q(rule_kind="percent")
                        & Q(percent_basis_points__isnull=False)
                        & Q(fixed_cents__isnull=True)
                        & Q(percent_basis_points__lte=10000)
                    )
                    | (
                        Q(rule_kind="fixed_cents")
                        & Q(fixed_cents__isnull=False)
                        & Q(percent_basis_points__isnull=True)
                    )
                ),
                name="ck_scheduling_commission_rule_kind",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "priority"]),
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.rule_kind} prio={self.priority}"


class AppointmentFinancial(TenantOwnedModel):
    class BalancePaymentMethod(models.TextChoices):
        CASH = "cash", "Dinheiro"
        PIX = "pix", "Pix"
        DEBIT = "debit", "Débito"
        CREDIT = "credit", "Crédito"
        OTHER = "other", "Outro"

    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name="financial",
        verbose_name="Agendamento",
    )
    service_price_cents = models.BigIntegerField(
        default=0, verbose_name="Preço do serviço"
    )
    deposit_paid_cents = models.BigIntegerField(default=0, verbose_name="Sinal pago")
    discount_cents = models.BigIntegerField(default=0, verbose_name="Desconto")
    discount_reason = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Motivo do desconto"
    )
    balance_payment_method = models.CharField(
        max_length=16,
        choices=BalancePaymentMethod.choices,
        blank=True,
        default="",
        verbose_name="Método do saldo",
    )
    deposit_recorded_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Sinal registrado em"
    )
    settled_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Liquidado em"
    )

    class Meta:
        verbose_name = "Financeiro do agendamento"
        verbose_name_plural = "Financeiros dos agendamentos"
        constraints = [
            models.CheckConstraint(
                condition=Q(service_price_cents__gte=0),
                name="ck_scheduling_fin_price_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(deposit_paid_cents__gte=0),
                name="ck_scheduling_fin_deposit_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(discount_cents__gte=0),
                name="ck_scheduling_fin_discount_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(
                    service_price_cents__gte=F("deposit_paid_cents") + F("discount_cents")
                ),
                name="ck_scheduling_fin_deposit_discount_lte_price",
            ),
        ]

    @property
    def balance_due_cents(self) -> int:
        return max(
            0,
            int(self.service_price_cents)
            - int(self.deposit_paid_cents)
            - int(self.discount_cents),
        )

    def __str__(self) -> str:
        return f"financial:{self.appointment_id}"


class CommissionEntry(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        APPROVED = "approved", "Aprovada"
        PAID = "paid", "Paga"
        CANCELLED = "cancelled", "Cancelada"

    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name="commission_entry",
        verbose_name="Agendamento",
    )
    professional = models.ForeignKey(
        Professional,
        on_delete=models.PROTECT,
        related_name="commission_entries",
        verbose_name="Profissional",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commission_entries",
        verbose_name="Serviço",
    )
    branch_id = models.UUIDField(null=True, blank=True, verbose_name="Unidade (UUID)")
    commission_rule = models.ForeignKey(
        CommissionRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entries",
        verbose_name="Regra",
    )
    base_amount_cents = models.BigIntegerField(verbose_name="Base")
    commission_cents = models.BigIntegerField(verbose_name="Comissão")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Lançamento de comissão"
        verbose_name_plural = "Lançamentos de comissão"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "appointment"],
                name="uq_scheduling_commission_entry_appointment",
            ),
            models.CheckConstraint(
                condition=Q(base_amount_cents__gte=0),
                name="ck_scheduling_commission_base_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(commission_cents__gte=0),
                name="ck_scheduling_commission_amount_nonneg",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "professional", "status"]),
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"commission:{self.appointment_id}={self.commission_cents}"
