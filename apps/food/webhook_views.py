"""Webhook público Mercado Pago — EXEQ Hub Food."""

from __future__ import annotations

import hashlib
import hmac
import json

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.billing.webhook_security import webhook_ip_allowed
from apps.food.exceptions import FoodInvalidOrderError
from apps.food.payments.mercadopago.webhook import (
    FoodPaymentNotFoundError,
    InvalidFoodWebhookSignatureError,
    ingest_mercadopago_webhook,
)


class FoodMercadoPagoWebhookThrottle(AnonRateThrottle):
    rate = "120/min"


class MercadoPagoFoodWebhookView(APIView):
    """POST /api/v1/food/webhooks/mercadopago — confirma FoodPayment → pedido pago."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [FoodMercadoPagoWebhookThrottle]

    def post(self, request):
        if not webhook_ip_allowed(request):
            return Response(
                {"detail": "Origem não autorizada", "code": "forbidden"},
                status=403,
            )
        raw = request.body
        if len(raw) > 256_000:
            return Response({"detail": "Payload muito grande"}, status=413)
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return Response({"detail": "JSON inválido"}, status=400)
        if not isinstance(payload, dict):
            return Response({"detail": "Payload inválido"}, status=400)

        query_params = {k: str(v) for k, v in request.GET.items()}
        try:
            event = ingest_mercadopago_webhook(
                raw_body=raw,
                payload=payload,
                x_signature=request.headers.get("x-signature", ""),
                x_request_id=request.headers.get("x-request-id", ""),
                query_params=query_params,
            )
        except InvalidFoodWebhookSignatureError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=401)
        except FoodPaymentNotFoundError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=404)
        except FoodInvalidOrderError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)

        payment = event.payment
        return Response(
            {
                "event_id": event.event_id,
                "payment_id": str(payment.id),
                "provider_payment_id": payment.provider_payment_id,
                "payment_status": payment.status,
                "order_id": str(payment.order_id),
            },
            status=200,
        )


def sign_mercadopago_webhook_test(
    *,
    secret: str,
    data_id: str,
    request_id: str,
    ts: str = "1704908010",
) -> str:
    """Helper de teste — gera header x-signature válido."""
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"ts={ts},v1={v1}"
