from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import ElectronicProxy
from apps.accounts.permissions import IsTenantMember, IsTenantWriter
from apps.master_data.models import Provider
from shared.validators import validate_cnpj


class ElectronicProxySerializer(serializers.ModelSerializer):
    class Meta:
        model = ElectronicProxy
        fields = (
            "id",
            "provider",
            "principal_cnpj",
            "proxy_document",
            "proxy_document_type",
            "ecac_service_codes",
            "status",
            "valid_from",
            "valid_to",
            "label",
            "metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ElectronicProxyCreateSerializer(serializers.Serializer):
    principal_cnpj = serializers.CharField(max_length=18)
    proxy_document = serializers.CharField(max_length=18)
    proxy_document_type = serializers.ChoiceField(
        choices=ElectronicProxy.DocumentType.choices,
        default=ElectronicProxy.DocumentType.CNPJ,
    )
    ecac_service_codes = serializers.ListField(
        child=serializers.CharField(max_length=32),
        required=False,
        default=list,
    )
    status = serializers.ChoiceField(
        choices=ElectronicProxy.Status.choices,
        default=ElectronicProxy.Status.ACTIVE,
    )
    valid_from = serializers.DateField()
    valid_to = serializers.DateField(required=False, allow_null=True)
    label = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    provider_id = serializers.UUIDField(required=False, allow_null=True)
    metadata = serializers.DictField(required=False, default=dict)

    def create(self, validated_data):
        tenant = self.context["request"].tenant
        principal = validate_cnpj(validated_data["principal_cnpj"])
        proxy_doc = "".join(ch for ch in validated_data["proxy_document"] if ch.isdigit())
        provider = None
        provider_id = validated_data.get("provider_id")
        if provider_id:
            provider = Provider.objects.get(id=provider_id, tenant=tenant)
        codes = validated_data.get("ecac_service_codes") or ["PGDASD", "GERARDAS12"]
        return ElectronicProxy.objects.create(
            tenant=tenant,
            provider=provider,
            principal_cnpj=principal,
            proxy_document=proxy_doc,
            proxy_document_type=validated_data["proxy_document_type"],
            ecac_service_codes=codes,
            status=validated_data["status"],
            valid_from=validated_data["valid_from"],
            valid_to=validated_data.get("valid_to"),
            label=validated_data.get("label") or "",
            metadata=validated_data.get("metadata") or {},
        )


class ElectronicProxyListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTenantWriter()]
        return [IsTenantMember()]

    def get(self, request):
        qs = ElectronicProxy.objects.filter(tenant=request.tenant).order_by("-created_at")
        return Response(ElectronicProxySerializer(qs, many=True).data)

    def post(self, request):
        ser = ElectronicProxyCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        try:
            proxy = ser.save()
        except Provider.DoesNotExist:
            return Response({"detail": "provider_id inválido"}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            ElectronicProxySerializer(proxy).data,
            status=status.HTTP_201_CREATED,
        )
