from rest_framework import serializers

from apps.fiscal.models import FiscalProfile
from apps.issuance.models import NfIssue
from apps.issuance.services import create_nf_issue
from apps.master_data.models import Customer, Provider, ServiceCatalogItem


class NfIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = NfIssue
        fields = (
            "id",
            "idempotency_key",
            "status",
            "provider",
            "customer",
            "service",
            "fiscal_profile",
            "ibge_code",
            "competence_date",
            "amount_cents",
            "resolved_params",
            "focus_ref",
            "correlation_id",
            "rejection_code",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "resolved_params",
            "focus_ref",
            "correlation_id",
            "rejection_code",
            "created_at",
            "updated_at",
        )


class NfIssueCancelSerializer(serializers.Serializer):
    justificativa = serializers.CharField(min_length=15, max_length=255)
    codigo_cancelamento = serializers.IntegerField(required=False, allow_null=True)


class NfIssueCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    provider_id = serializers.UUIDField()
    customer_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    fiscal_profile_id = serializers.UUIDField()
    ibge_code = serializers.CharField(max_length=7)
    competence_date = serializers.DateField()
    amount_cents = serializers.IntegerField(min_value=1)

    def create(self, validated_data):
        tenant = self.context["request"].tenant

        def owned(model, pk):
            return model.objects.get(id=pk, tenant=tenant)

        try:
            provider = owned(Provider, validated_data["provider_id"])
            customer = owned(Customer, validated_data["customer_id"])
            service = owned(ServiceCatalogItem, validated_data["service_id"])
            profile = owned(FiscalProfile, validated_data["fiscal_profile_id"])
        except (
            Provider.DoesNotExist,
            Customer.DoesNotExist,
            ServiceCatalogItem.DoesNotExist,
            FiscalProfile.DoesNotExist,
        ) as exc:
            raise serializers.ValidationError("Referência inválida para o tenant") from exc

        return create_nf_issue(
            tenant=tenant,
            idempotency_key=validated_data["idempotency_key"],
            provider=provider,
            customer=customer,
            service=service,
            fiscal_profile=profile,
            ibge_code=validated_data["ibge_code"],
            competence_date=validated_data["competence_date"],
            amount_cents=validated_data["amount_cents"],
        )
