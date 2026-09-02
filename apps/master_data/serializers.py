from rest_framework import serializers

from apps.master_data.models import Customer, Provider, ServiceCatalogItem
from apps.master_data.services import create_customer, create_provider, create_service

CADASTRAL_FIELDS = (
    "situacao_cadastral",
    "data_abertura",
    "cnae_principal",
    "natureza_juridica",
    "porte",
    "whatsapp",
    "contato_nome",
    "data_source",
    "receita_raw_payload",
    "last_lookup_at",
)


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = (
            "id",
            "document",
            "legal_name",
            "trade_name",
            "municipal_registration",
            "state_registration",
            "tax_regime",
            "address",
            "is_active",
            *CADASTRAL_FIELDS,
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "last_lookup_at")

    def create(self, validated_data):
        from apps.accounts.plan_limits import PlanLimitError

        try:
            return create_provider(tenant=self.context["request"].tenant, **validated_data)
        except PlanLimitError as exc:
            raise serializers.ValidationError({"non_field_errors": [str(exc)]}) from exc
        except ValueError as exc:
            raise serializers.ValidationError({"document": str(exc)}) from exc

    def update(self, instance, validated_data):
        from apps.accounts.plan_limits import PlanLimitError, assert_can_add_active_provider

        will_activate = validated_data.get("is_active", instance.is_active)
        if will_activate and not instance.is_active:
            try:
                assert_can_add_active_provider(instance.tenant)
            except PlanLimitError as exc:
                raise serializers.ValidationError({"is_active": [str(exc)]}) from exc
        return super().update(instance, validated_data)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = (
            "id",
            "document",
            "document_type",
            "name",
            "email",
            "address",
            "is_active",
            *CADASTRAL_FIELDS,
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "last_lookup_at")

    def create(self, validated_data):
        try:
            return create_customer(tenant=self.context["request"].tenant, **validated_data)
        except ValueError as exc:
            raise serializers.ValidationError({"document": str(exc)}) from exc


class ServiceCatalogItemSerializer(serializers.ModelSerializer):
    display_label = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCatalogItem
        fields = (
            "id",
            "service_code",
            "description",
            "lc116_item",
            "codigo_tributacao_nacional_iss",
            "codigo_nbs",
            "nbs_item",
            "display_label",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "display_label", "nbs_item", "created_at", "updated_at")

    def get_display_label(self, obj) -> str:
        from apps.master_data.national_service_import import service_catalog_display_label

        return service_catalog_display_label(
            service_code=obj.service_code,
            codigo_tributacao_nacional_iss=obj.codigo_tributacao_nacional_iss,
            description=obj.description,
        )

    def create(self, validated_data):
        return create_service(tenant=self.context["request"].tenant, **validated_data)


class DocumentLookupSerializer(serializers.Serializer):
    document = serializers.CharField(max_length=18)
    force = serializers.BooleanField(required=False, default=False)
    persist = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Se true e já existir cadastro do documento, atualiza last_lookup_at/payload.",
    )


class CepLookupSerializer(serializers.Serializer):
    cep = serializers.CharField(max_length=12)
