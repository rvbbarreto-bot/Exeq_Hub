import json

from rest_framework import serializers

from apps.billing.models import Charge, WebhookInbox
from apps.billing.exceptions import GatewayRegistrationError
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
            "gateway_ref",
            "nf_issue",
            "correlation_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "gateway_ref",
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

        try:
            return create_charge(
                tenant=tenant,
                idempotency_key=validated_data["idempotency_key"],
                customer=customer,
                amount_cents=validated_data["amount_cents"],
                due_date=validated_data["due_date"],
                description=validated_data.get("description", ""),
                nf_issue=nf_issue,
            )
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
