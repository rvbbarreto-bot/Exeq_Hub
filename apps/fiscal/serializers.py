from rest_framework import serializers

from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.fiscal.tax_engine import add_rule, create_catalog


class FiscalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalProfile
        fields = (
            "id",
            "name",
            "tax_regime",
            "iss_retention_policy",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        return FiscalProfile.objects.create(
            tenant=self.context["request"].tenant,
            **validated_data,
        )


class TaxRuleCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRuleCatalog
        fields = (
            "id",
            "version",
            "status",
            "publish_checklist",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "version",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        return create_catalog(tenant=self.context["request"].tenant)


class MunicipalTaxRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MunicipalTaxRule
        fields = (
            "id",
            "catalog",
            "fiscal_profile",
            "ibge_code",
            "municipio_nome",
            "uf",
            "service_code",
            "tax_regime",
            "iss_rate",
            "irrf_rate",
            "pis_rate",
            "cofins_rate",
            "iss_retained",
            "simples_codigo_tributacao",
            "valid_from",
            "valid_to",
            "priority",
            "focus_field_overrides",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        catalog = validated_data.pop("catalog")
        fiscal_profile = validated_data.pop("fiscal_profile")
        if catalog.tenant_id != self.context["request"].tenant.id:
            raise serializers.ValidationError({"catalog": "Catálogo inválido"})
        if fiscal_profile.tenant_id != self.context["request"].tenant.id:
            raise serializers.ValidationError({"fiscal_profile": "Perfil inválido"})
        from apps.fiscal.exceptions import CatalogNotEditableError

        try:
            return add_rule(catalog=catalog, fiscal_profile=fiscal_profile, **validated_data)
        except CatalogNotEditableError as exc:
            raise serializers.ValidationError({"catalog": str(exc)}) from exc


class TaxResolveSerializer(serializers.Serializer):
    fiscal_profile_id = serializers.UUIDField()
    ibge_code = serializers.CharField(max_length=7)
    service_code = serializers.CharField(max_length=32)
    tax_regime = serializers.CharField(max_length=32)
    competence_date = serializers.DateField()
