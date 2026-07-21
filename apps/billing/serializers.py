import json

from rest_framework import serializers

from apps.billing.exceptions import GatewayRegistrationError, InvalidChargeInputError
from apps.billing.models import Charge, WebhookInbox
from apps.billing.services import create_charge
from apps.issuance.models import NfIssue
from apps.master_data.models import Customer


class ChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Charge
        fields = (
            "id",
            "idempotency_key",
            "status",
            "customer",
            "amount_cents",
            "due_date",
            "description",
            "seu_numero",
            "charge_kind",
            "message_lines",
            "schedule_group_id",
            "installment_number",
            "installment_count",
            "num_dias_agenda",
            "multa_percent",
            "mora_percent_am",
            "gateway_ref",
            "digitable_line",
            "barcode",
            "pix_copy_paste",
            "payment_url",
            "nf_issue",
            "correlation_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "gateway_ref",
            "digitable_line",
            "barcode",
            "pix_copy_paste",
            "payment_url",
            "schedule_group_id",
            "installment_number",
            "installment_count",
            "num_dias_agenda",
            "multa_percent",
            "mora_percent_am",
            "message_lines",
            "correlation_id",
            "created_at",
            "updated_at",
        )


class ChargeCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    customer_id = serializers.UUIDField()
    amount_cents = serializers.IntegerField(min_value=1)
    due_date = serializers.DateField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    seu_numero = serializers.CharField(
        required=False, allow_blank=True, max_length=15, default=""
    )
    message_lines = serializers.ListField(
        child=serializers.CharField(allow_blank=True, max_length=78),
        required=False,
        allow_empty=True,
        max_length=5,
    )
    charge_kind = serializers.ChoiceField(
        choices=Charge.ChargeKind.choices,
        required=False,
        default=Charge.ChargeKind.SIMPLE,
    )
    installment_count = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=60
    )
    recurrence_end_date = serializers.DateField(required=False, allow_null=True)
    nf_issue_id = serializers.UUIDField(required=False, allow_null=True)

    def create(self, validated_data):
        tenant = self.context["request"].tenant
        try:
            customer = Customer.objects.get(
                id=validated_data["customer_id"],
                tenant=tenant,
            )
        except Customer.DoesNotExist as exc:
            raise serializers.ValidationError({"customer_id": "Cliente inválido"}) from exc

        nf_issue = None
        nf_issue_id = validated_data.get("nf_issue_id")
        if nf_issue_id:
            try:
                nf_issue = NfIssue.objects.get(id=nf_issue_id, tenant=tenant)
            except NfIssue.DoesNotExist as exc:
                raise serializers.ValidationError({"nf_issue_id": "Nota inválida"}) from exc

        seu = (validated_data.get("seu_numero") or "").strip() or None
        try:
            return create_charge(
                tenant=tenant,
                idempotency_key=validated_data["idempotency_key"],
                customer=customer,
                amount_cents=validated_data["amount_cents"],
                due_date=validated_data["due_date"],
                description=validated_data.get("description", ""),
                nf_issue=nf_issue,
                seu_numero=seu,
                message_lines=validated_data.get("message_lines"),
                charge_kind=validated_data.get(
                    "charge_kind", Charge.ChargeKind.SIMPLE
                ),
                installment_count=validated_data.get("installment_count"),
                recurrence_end_date=validated_data.get("recurrence_end_date"),
            )
        except InvalidChargeInputError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        except GatewayRegistrationError as exc:
            raise serializers.ValidationError({"gateway": str(exc)}) from exc


class WebhookInboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookInbox
        fields = (
            "id",
            "provider",
            "idempotency_key",
            "status",
            "signature_valid",
            "error_message",
            "processed_at",
            "created_at",
        )
        read_only_fields = fields


def dumps_canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
