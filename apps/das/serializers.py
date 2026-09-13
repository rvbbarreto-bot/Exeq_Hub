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
    has_pdf = serializers.SerializerMethodField()

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
            "has_pdf",
            "versao_atual",
            "idempotency_key",
            "metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_has_pdf(self, obj: GuiaFiscal) -> bool:
        return bool(obj.pdf_file_id)


class GuiaFiscalCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    provider_id = serializers.UUIDField()
    tipo_guia = serializers.ChoiceField(choices=GuiaFiscal.TipoGuia.choices)
    competencia = serializers.RegexField(regex=r"^\d{4}-\d{2}$")
    versao_atual = serializers.IntegerField(min_value=1, default=1, required=False)
    delivery_email = serializers.EmailField(required=False, allow_blank=True)
    delivery_phone = serializers.CharField(required=False, allow_blank=True, max_length=32)

    def create(self, validated_data):
        tenant = self.context["request"].tenant
        delivery_email = (validated_data.pop("delivery_email", "") or "").strip()
        delivery_phone = (validated_data.pop("delivery_phone", "") or "").strip()
        delivery_payload = {}
        if delivery_email:
            delivery_payload["delivery_email"] = delivery_email
        if delivery_phone:
            delivery_payload["delivery_phone"] = delivery_phone
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
                delivery_payload=delivery_payload or None,
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
