from rest_framework import serializers

from apps.scheduling.models import (
    Appointment,
    AppointmentFinancial,
    BusinessHours,
    CalendarBlock,
    CommissionEntry,
    CommissionRule,
    Professional,
    ProfessionalService,
    Service,
)
from apps.scheduling.services import create_appointment
from apps.scheduling.finance import (
    FinancialError,
    CommissionEntryNotFoundError,
    record_deposit,
    settle_financial,
    set_commission_entry_status,
)
from apps.scheduling.exceptions import (
    AppointmentInPastError,
    AppointmentNotFoundError,
    CustomerNotFoundError,
    CustomerRestrictedError,
    DuplicateIdempotencyKeyError,
    InvalidAppointmentTransitionError,
    ProfessionalNotFoundError,
    ScheduleDurationMismatchError,
    SchedulingError,
    ServiceNotBookableError,
    ServicePriceMismatchError,
    SlotUnavailableError,
)


class ProfessionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Professional
        fields = (
            "id",
            "provider",
            "user",
            "name",
            "timezone",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        return super().create(validated_data)


class ScheduleServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = (
            "id",
            "catalog_item",
            "name",
            "duration_minutes",
            "price_cents",
            "buffer_before_minutes",
            "buffer_after_minutes",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        return super().create(validated_data)


class ProfessionalServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfessionalService
        fields = ("id", "professional", "service", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        return super().create(validated_data)


class BusinessHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHours
        fields = (
            "id",
            "professional",
            "weekday",
            "starts_at",
            "ends_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        return super().create(validated_data)


class CalendarBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarBlock
        fields = (
            "id",
            "professional",
            "starts_at",
            "ends_at",
            "reason",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "created_at", "updated_at")

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["tenant"] = request.tenant
        validated_data["created_by"] = request.user
        return super().create(validated_data)


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = (
            "id",
            "professional",
            "customer",
            "service",
            "starts_at",
            "ends_at",
            "price_cents",
            "status",
            "source",
            "explicit_confirmation",
            "notes",
            "idempotency_key",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AppointmentCreateSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    professional_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    price_cents = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    source = serializers.ChoiceField(
        choices=Appointment.Source.choices, default=Appointment.Source.ADMIN
    )
    idempotency_key = serializers.CharField(min_length=8, max_length=128)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    explicit_confirmation = serializers.BooleanField(default=False)

    def create(self, validated_data):
        request = self.context["request"]
        try:
            return create_appointment(
                tenant=request.tenant,
                customer_id=validated_data["customer_id"],
                professional_id=validated_data["professional_id"],
                service_id=validated_data["service_id"],
                starts_at=validated_data["starts_at"],
                ends_at=validated_data.get("ends_at"),
                price_cents=validated_data.get("price_cents"),
                source=validated_data.get("source", Appointment.Source.ADMIN),
                idempotency_key=validated_data["idempotency_key"],
                notes=validated_data.get("notes") or "",
                explicit_confirmation=validated_data.get(
                    "explicit_confirmation", False
                ),
                is_staff=True,
            )
        except (
            ServiceNotBookableError,
            AppointmentInPastError,
            SlotUnavailableError,
            ScheduleDurationMismatchError,
            ServicePriceMismatchError,
            CustomerRestrictedError,
            DuplicateIdempotencyKeyError,
            ProfessionalNotFoundError,
            CustomerNotFoundError,
            SchedulingError,
        ) as exc:
            raise serializers.ValidationError(
                {"detail": str(exc), "code": getattr(exc, "code", "scheduling_error")}
            ) from exc


class AvailabilityQuerySerializer(serializers.Serializer):
    professional_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    day = serializers.DateField()
    slot_interval_minutes = serializers.IntegerField(
        required=False, default=30, min_value=5, max_value=120
    )


class AppointmentFinancialSerializer(serializers.ModelSerializer):
    balance_due_cents = serializers.IntegerField(read_only=True)

    class Meta:
        model = AppointmentFinancial
        fields = (
            "id",
            "appointment",
            "service_price_cents",
            "deposit_paid_cents",
            "discount_cents",
            "discount_reason",
            "balance_payment_method",
            "deposit_recorded_at",
            "settled_at",
            "balance_due_cents",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DepositSerializer(serializers.Serializer):
    deposit_paid_cents = serializers.IntegerField(min_value=0)

    def save(self, **kwargs):
        request = self.context["request"]
        appointment_id = self.context["appointment_id"]
        try:
            return record_deposit(
                tenant=request.tenant,
                appointment_id=appointment_id,
                deposit_paid_cents=self.validated_data["deposit_paid_cents"],
            )
        except (AppointmentNotFoundError, FinancialError) as exc:
            raise serializers.ValidationError(
                {"detail": str(exc), "code": getattr(exc, "code", "financial_error")}
            ) from exc


class SettleFinancialSerializer(serializers.Serializer):
    balance_payment_method = serializers.ChoiceField(
        choices=AppointmentFinancial.BalancePaymentMethod.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    discount_cents = serializers.IntegerField(required=False, default=0, min_value=0)
    discount_reason = serializers.CharField(
        required=False, allow_blank=True, default=""
    )

    def save(self, **kwargs):
        request = self.context["request"]
        try:
            return settle_financial(
                tenant=request.tenant,
                appointment_id=self.context["appointment_id"],
                balance_payment_method=self.validated_data.get(
                    "balance_payment_method"
                )
                or "",
                discount_cents=self.validated_data.get("discount_cents") or 0,
                discount_reason=self.validated_data.get("discount_reason") or "",
            )
        except (AppointmentNotFoundError, FinancialError) as exc:
            raise serializers.ValidationError(
                {"detail": str(exc), "code": getattr(exc, "code", "financial_error")}
            ) from exc


class CommissionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionRule
        fields = (
            "id",
            "branch_id",
            "professional",
            "service",
            "rule_kind",
            "percent_basis_points",
            "fixed_cents",
            "priority",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["tenant"] = self.context["request"].tenant
        return super().create(validated_data)


class CommissionEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionEntry
        fields = (
            "id",
            "appointment",
            "professional",
            "service",
            "branch_id",
            "commission_rule",
            "base_amount_cents",
            "commission_cents",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CommissionEntryStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CommissionEntry.Status.choices)

    def save(self, **kwargs):
        request = self.context["request"]
        try:
            return set_commission_entry_status(
                tenant=request.tenant,
                entry_id=self.context["entry_id"],
                status=self.validated_data["status"],
            )
        except (
            CommissionEntryNotFoundError,
            FinancialError,
            InvalidAppointmentTransitionError,
        ) as exc:
            raise serializers.ValidationError(
                {"detail": str(exc), "code": getattr(exc, "code", "financial_error")}
            ) from exc

