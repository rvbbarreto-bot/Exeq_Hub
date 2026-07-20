from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.accounts.secrets import get_tenant_secret_plaintext
from integrations.nfse.focus import FocusHttpError
from integrations.nfse.municipios import FocusMunicipioClient


class FocusMunicipioView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request, ibge_code: str):
        if not ibge_code.isdigit() or len(ibge_code) != 7:
            return Response({"detail": "ibge_code deve ter 7 dígitos"}, status=400)
        token = get_tenant_secret_plaintext(
            tenant=request.tenant,
            provider="focus",
            key_name="api_token",
        )
        client = FocusMunicipioClient(token=token or None)
        try:
            municipio = client.get_municipio(ibge_code)
            exemplo = client.get_json_exemplo(ibge_code)
            overrides = client.suggested_overrides(ibge_code)
        except FocusHttpError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(
            {
                "ibge_code": ibge_code,
                "municipio": municipio,
                "json_exemplo": exemplo,
                "suggested_overrides": overrides,
            }
        )
