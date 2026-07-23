"""API — configuração do provedor de cobrança do tenant."""

from __future__ import annotations

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantAdmin, IsTenantMember, IsTenantWriter
from apps.billing.exceptions import (
    InvalidPaymentProviderError,
    InvalidProviderCredentialsError,
)
from apps.billing.provider_services import (
    delete_inter_webhook,
    get_billing_provider_status,
    get_inter_credentials_metadata,
    get_inter_webhook,
    get_token_provider_metadata,
    register_inter_webhook,
    retry_inter_webhook_callbacks,
    save_inter_credentials,
    save_token_provider_credentials,
    set_billing_provider,
    test_inter_connection,
)
from integrations.payments.errors import PaymentGatewayError
from integrations.payments.router import PROVIDER_ASAAS, PROVIDER_C6, PROVIDER_INTER


def _decode_upload(upload) -> str:
    if upload is None:
        return ""
    raw = upload.read()
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


class BillingProviderView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsTenantMember()]
        return [IsTenantAdmin()]

    def get(self, request):
        return Response(get_billing_provider_status(tenant=request.tenant))

    def put(self, request):
        provider = request.data.get("provider")
        try:
            data = set_billing_provider(
                tenant=request.tenant,
                provider=provider,
                actor_user=request.user,
            )
        except InvalidPaymentProviderError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data, status=200)


class InterCredentialsView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsTenantMember()]
        return [IsTenantAdmin()]

    def get(self, request):
        return Response(get_inter_credentials_metadata(tenant=request.tenant))

    def post(self, request):
        cert_pem = _decode_upload(request.FILES.get("cert_file")) or (
            request.data.get("cert_pem") or ""
        )
        key_pem = _decode_upload(request.FILES.get("key_file")) or (
            request.data.get("key_pem") or ""
        )
        try:
            data = save_inter_credentials(
                tenant=request.tenant,
                client_id=request.data.get("client_id") or "",
                client_secret=request.data.get("client_secret") or "",
                cert_pem=cert_pem,
                key_pem=key_pem,
                conta_corrente=request.data.get("conta_corrente") or "",
                actor_user=request.user,
            )
        except InvalidProviderCredentialsError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data, status=200)


class TokenProviderCredentialsView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsTenantMember()]
        return [IsTenantAdmin()]

    def get(self, request, provider: str):
        try:
            return Response(
                get_token_provider_metadata(
                    tenant=request.tenant, provider=provider
                )
            )
        except InvalidPaymentProviderError as exc:
            return Response({"detail": str(exc)}, status=404)

    def post(self, request, provider: str):
        try:
            data = save_token_provider_credentials(
                tenant=request.tenant,
                provider=provider,
                api_token=request.data.get("api_token") or "",
                actor_user=request.user,
            )
        except InvalidPaymentProviderError as exc:
            return Response({"detail": str(exc)}, status=404)
        except InvalidProviderCredentialsError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data, status=200)


class InterTestConnectionView(APIView):
    permission_classes = [IsTenantAdmin]

    def post(self, request):
        result = test_inter_connection(
            tenant=request.tenant, actor_user=request.user
        )
        http_status = result.pop("http_status", 200)
        return Response(result, status=http_status)


class InterWebhookView(APIView):
    """D1 — PUT/GET/DELETE webhook Cobrança Inter (estudo §9.1)."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsTenantMember()]
        return [IsTenantAdmin()]

    def get(self, request):
        try:
            return Response(get_inter_webhook(tenant=request.tenant))
        except (InvalidPaymentProviderError, InvalidProviderCredentialsError) as exc:
            return Response({"detail": str(exc)}, status=400)

    def put(self, request):
        try:
            data = register_inter_webhook(
                tenant=request.tenant,
                webhook_url=request.data.get("webhookUrl")
                or request.data.get("webhook_url"),
                actor_user=request.user,
            )
        except InvalidPaymentProviderError as exc:
            return Response({"detail": str(exc)}, status=400)
        except InvalidProviderCredentialsError as exc:
            return Response({"detail": str(exc)}, status=400)
        except PaymentGatewayError as exc:
            return Response({"detail": str(exc)}, status=502)
        return Response(data, status=200)

    def delete(self, request):
        try:
            data = delete_inter_webhook(
                tenant=request.tenant, actor_user=request.user
            )
        except (InvalidPaymentProviderError, InvalidProviderCredentialsError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data, status=200)


class InterWebhookRetryView(APIView):
    """D2 — POST retry de callbacks Inter (+ reprocess inbox Hub failed)."""

    permission_classes = [IsTenantAdmin]

    def post(self, request):
        refs = (
            request.data.get("codigoSolicitacao")
            or request.data.get("codigo_solicitacao")
            or []
        )
        if isinstance(refs, str):
            refs = [refs]
        if not isinstance(refs, list):
            return Response(
                {"detail": "codigoSolicitacao deve ser lista"},
                status=400,
            )
        reprocess = request.data.get("reprocess_local_inbox", True)
        try:
            data = retry_inter_webhook_callbacks(
                tenant=request.tenant,
                codigo_solicitacao=refs,
                actor_user=request.user,
                reprocess_local_inbox=bool(reprocess),
            )
        except (InvalidPaymentProviderError, InvalidProviderCredentialsError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(data, status=200)


# aliases para clareza de import
ASAAS = PROVIDER_ASAAS
C6 = PROVIDER_C6
INTER = PROVIDER_INTER
