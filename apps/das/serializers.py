from rest_framework import serializers

from apps.accounts.exceptions import CertificateNotUsableError, ElectronicProxyNotUsableError
from apps.das.exceptions import DuplicateDasNaturalKeyError
from apps.das.models import GuiaFiscal
from apps.das.services import emitir_guia
from apps.master_data.models import Provider
from integrations.receita.exceptions import (
    ReceitaAuthError,
    ReceitaBusinessError,
    ReceitaCredentialsMissingError,
    ReceitaHttpError,
    ReceitaHttpNotConfiguredError,
)


class GuiaFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuiaFiscal
        fields = (
            "id",
            "provider",
            "tipo_guia",
            "competencia",
            "data_vencimento",
            "valor_principal",
            "valor_multa",
            "valor_juros",
            "valor_total",
            "linha_digitavel",
            "pix_copia_cola",
            "status",
            "compliance_status",
            "compliance_motivo",
            "pdf_storage_key",
            "pdf_file",
            "versao_atual",
            "idempotency_key",
            "metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class GuiaFiscalCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    provider_id = serializers.UUIDField()
    tipo_guia = serializers.ChoiceField(choices=GuiaFiscal.TipoGuia.choices)
    competencia = serializers.RegexField(regex=r"^\d{4}-\d{2}$")
    versao_atual = serializers.IntegerField(min_value=1, default=1, required=False)

    def create(self, validated_data):
        tenant = self.context["request"].tenant
        try:
            provider = Provider.objects.get(
                id=validated_data["provider_id"],
                tenant=tenant,
            )
        except Provider.DoesNotExist as exc:
            raise serializers.ValidationError({"provider_id": "Prestador inválido"}) from exc
        try:
            return emitir_guia(
                tenant=tenant,
                idempotency_key=validated_data["idempotency_key"],
                provider=provider,
                tipo_guia=validated_data["tipo_guia"],
                competencia=validated_data["competencia"],
                versao_atual=validated_data.get("versao_atual", 1),
            )
        except DuplicateDasNaturalKeyError as exc:
            raise serializers.ValidationError({"detail": str(exc), "code": exc.code}) from exc
        except CertificateNotUsableError as exc:
            raise serializers.ValidationError({"detail": str(exc), "code": exc.code}) from exc
        except ElectronicProxyNotUsableError as exc:
            raise serializers.ValidationError({"detail": str(exc), "code": exc.code}) from exc
        except (
            ReceitaHttpNotConfiguredError,
            ReceitaCredentialsMissingError,
            ReceitaAuthError,
            ReceitaHttpError,
            ReceitaBusinessError,
        ) as exc:
            raise serializers.ValidationError(
                {"detail": str(exc), "code": getattr(exc, "code", "receita_error")}
            ) from exc
