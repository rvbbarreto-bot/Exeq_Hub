from rest_framework import serializers

from apps.master_data.models import Customer, Provider, ServiceCatalogItem
from apps.master_data.services import create_customer, create_provider, create_service


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Provider
        fields = (
            "id",
            "document",
            "legal_name",
            "trade_name",
            "municipal_registration",
            "tax_regime",
            "address",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        try:
            return create_provider(tenant=self.context["request"].tenant, **validated_data)
        except ValueError as exc:
            raise serializers.ValidationError({"document": str(exc)}) from exc


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
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        try:
            return create_customer(tenant=self.context["request"].tenant, **validated_data)
        except ValueError as exc:
            raise serializers.ValidationError({"document": str(exc)}) from exc


class ServiceCatalogItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCatalogItem
        fields = (
            "id",
            "service_code",
            "description",
            "lc116_item",
            "codigo_tributacao_nacional_iss",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        return create_service(tenant=self.context["request"].tenant, **validated_data)
