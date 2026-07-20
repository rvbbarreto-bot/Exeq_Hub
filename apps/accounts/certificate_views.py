from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.certificates import PfxParseError, upload_a1_certificate
from apps.accounts.models import DigitalCertificate
from apps.accounts.permissions import IsTenantWriter
from apps.accounts.secrets import set_tenant_secret
from shared.validators import validate_cnpj


class DigitalCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DigitalCertificate
        fields = (
            "id",
            "label",
            "cnpj",
            "cert_type",
            "is_primary",
            "version",
            "key_usage",
            "not_before",
            "not_after",
            "thumbprint_sha256",
            "status",
            "created_at",
        )
        read_only_fields = fields


class UploadCertificateView(APIView):
    permission_classes = [IsTenantWriter]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("file")
        label = request.data.get("label") or "A1"
        cnpj = request.data.get("cnpj")
        password = request.data.get("password") or ""
        if not upload or not cnpj:
            return Response({"detail": "file e cnpj obrigatórios"}, status=400)
        try:
            cnpj = validate_cnpj(cnpj)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        try:
            cert = upload_a1_certificate(
                tenant=request.tenant,
                label=label,
                cnpj=cnpj,
                pfx_bytes=upload.read(),
                password=password,
                actor_user=request.user,
            )
        except PfxParseError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(DigitalCertificateSerializer(cert).data, status=status.HTTP_201_CREATED)


class SetFocusTokenView(APIView):
    permission_classes = [IsTenantWriter]

    def post(self, request):
        token = request.data.get("token")
        if not token:
            return Response({"detail": "token obrigatório"}, status=400)
        set_tenant_secret(
            tenant=request.tenant,
            provider="focus",
            key_name="api_token",
            plaintext=token,
        )
        return Response({"status": "saved", "provider": "focus"}, status=200)


class RegisterFocusEmpresaView(APIView):
    permission_classes = [IsTenantWriter]

    def post(self, request):
        from apps.accounts.focus_empresa import register_provider_on_focus
        from apps.master_data.models import Provider
        from integrations.nfse.focus import FocusHttpError

        provider_id = request.data.get("provider_id")
        if not provider_id:
            return Response({"detail": "provider_id obrigatório"}, status=400)
        try:
            provider = Provider.objects.get(tenant=request.tenant, id=provider_id)
        except Provider.DoesNotExist:
            return Response({"detail": "provider não encontrado"}, status=404)
        try:
            result = register_provider_on_focus(
                tenant=request.tenant,
                provider=provider,
                enable_nfsen_homolog=bool(
                    request.data.get("habilita_nfsen_homologacao", True)
                ),
                enable_nfsen_producao=bool(
                    request.data.get("habilita_nfsen_producao", False)
                ),
                webhook_url=request.data.get("webhook_url"),
            )
        except FocusHttpError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(result, status=200)
