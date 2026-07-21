import json

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.billing.exceptions import (
    ChargeNotFoundError,
    GatewayRegistrationError,
    IncompatiblePaymentError,
    InvalidChargeInputError,
    InvalidWebhookSignatureError,
)
from apps.billing.models import Charge, WebhookInbox
from apps.billing.serializers import (
    ChargeCreateSerializer,
    ChargeSerializer,
    WebhookInboxSerializer,
)
from apps.billing.services import (
    cancel_charge,
    ingest_gateway_webhook,
    reprocess_webhook,
    sync_charge_from_gateway,
)


class ChargeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Charge.objects.filter(tenant=self.request.tenant).order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return ChargeCreateSerializer
        return ChargeSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        if isinstance(result, list):
            group_id = result[0].schedule_group_id if result else None
            return Response(
                {
                    "schedule_group_id": str(group_id) if group_id else None,
                    "charge_kind": result[0].charge_kind if result else None,
                    "charges": ChargeSerializer(result, many=True).data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(ChargeSerializer(result).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        charge = self.get_object()
        motivo = request.data.get("motivo_cancelamento") or request.data.get(
            "motivoCancelamento"
        )
        try:
            cancel_charge(charge, motivo_cancelamento=motivo)
        except InvalidChargeInputError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)
        except (IncompatiblePaymentError, GatewayRegistrationError) as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)
        charge.refresh_from_db()
        return Response(ChargeSerializer(charge).data)

    @action(detail=True, methods=["post", "get"], url_path="sync")
    def sync(self, request, pk=None):
        """Consulta situação/pagamento no gateway (Inter GET /cobrancas/{codigo})."""
        charge = self.get_object()
        try:
            sync_charge_from_gateway(charge)
        except ChargeNotFoundError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)
        except GatewayRegistrationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=502)
        charge.refresh_from_db()
        return Response(ChargeSerializer(charge).data)


class GatewayWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw = request.body
        signature = request.headers.get("X-Webhook-Signature", "")
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return Response({"detail": "JSON inválido"}, status=400)
        try:
            inbox = ingest_gateway_webhook(
                raw_body=raw,
                signature=signature,
                payload=payload,
            )
        except InvalidWebhookSignatureError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=401)
        except (ChargeNotFoundError, IncompatiblePaymentError, GatewayRegistrationError) as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)
        if inbox.status == WebhookInbox.Status.FAILED:
            code = (
                "incompatible_payment"
                if "incompatível" in (inbox.error_message or "").lower()
                or "incompativel" in (inbox.error_message or "").lower()
                else "charge_not_found"
            )
            if "Valor" in (inbox.error_message or ""):
                code = "incompatible_payment"
            return Response(
                {"detail": inbox.error_message or "Falha no webhook", "code": code},
                status=400,
            )
        return Response(WebhookInboxSerializer(inbox).data, status=200)


class WebhookInboxViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantWriter]
    serializer_class = WebhookInboxSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return WebhookInbox.objects.filter(tenant=self.request.tenant)

    @action(detail=True, methods=["post"], url_path="reprocess")
    def reprocess(self, request, pk=None):
        inbox = self.get_object()
        try:
            reprocess_webhook(inbox)
        except (ChargeNotFoundError, IncompatiblePaymentError, InvalidWebhookSignatureError) as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)
        inbox.refresh_from_db()
        if inbox.status == WebhookInbox.Status.FAILED:
            return Response(
                {
                    "detail": inbox.error_message or "Falha no reprocessamento",
                    "code": "webhook_failed",
                },
                status=400,
            )
        return Response(WebhookInboxSerializer(inbox).data)
