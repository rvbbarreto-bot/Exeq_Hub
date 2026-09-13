import logging

from rest_framework import serializers, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.channel.engine import process_inbound
from apps.channel.models import ChannelNotification, ChannelSession
from apps.channel.services import enqueue_notification
from apps.channel.webhook import (
    mask_phone,
    mask_sensitive,
    parse_inbound_payload,
    verify_webhook_token,
)

logger = logging.getLogger(__name__)


class EvolutionWebhookThrottle(AnonRateThrottle):
    """WA-SEC-04 — limita rajadas no webhook público."""

    scope = "webhook_evolution"


class ChannelSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChannelSession
        fields = (
            "id",
            "idempotency_key",
            "phone_e164",
            "status",
            "draft_payload",
            "nf_issue",
            "last_message_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ChannelNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChannelNotification
        fields = (
            "id",
            "phone_e164",
            "event_type",
            "message_body",
            "status",
            "provider",
            "provider_ref",
            "created_at",
        )
        read_only_fields = fields


class ChannelSessionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantWriter]
    serializer_class = ChannelSessionSerializer

    def get_queryset(self):
        # WA-SEC-03 — isolamento por tenant do JWT
        return ChannelSession.objects.filter(tenant=self.request.tenant)


class EvolutionWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EvolutionWebhookThrottle]

    def post(self, request):
        if not verify_webhook_token(request):
            return Response({"detail": "não autorizado", "code": "webhook_unauthorized"}, status=401)

        payload = request.data if isinstance(request.data, dict) else {}
        outcome = parse_inbound_payload(payload)

        if outcome.status == "ignored":
            return Response({"status": "ignored", "reason": outcome.reason}, status=200)

        if outcome.status != "ok" or outcome.inbound is None:
            code = outcome.reason or "payload_incompleto"
            http = 404 if code == "instancia_desconhecida" else 400
            return Response({"detail": code, "code": code}, status=http)

        inbound = outcome.inbound
        logger.info(
            "channel.webhook inbound tenant=%s phone=%s msg=%s text=%s",
            inbound.tenant.slug,
            mask_phone(inbound.phone_e164),
            inbound.message_id[:16],
            mask_sensitive(inbound.text)[:80],
        )

        session, reply = process_inbound(
            tenant=inbound.tenant,
            phone_e164=inbound.phone_e164,
            message_id=inbound.message_id,
            text=inbound.text,
        )
        if reply:
            enqueue_notification(
                tenant=inbound.tenant,
                phone_e164=inbound.phone_e164,
                event_type="channel.reply",
                message_body=reply,
                session=session,
            )
        data = ChannelSessionSerializer(session).data if session else {"status": "blocked"}
        data["reply"] = reply
        return Response(data, status=200)


class ChannelNotifyView(APIView):
    permission_classes = [IsTenantWriter]

    def post(self, request):
        phone = request.data.get("phone_e164")
        message_body = request.data.get("message_body")
        event_type = request.data.get("event_type", "manual")
        if not phone or not message_body:
            return Response({"detail": "phone_e164 e message_body obrigatórios"}, status=400)
        notification = enqueue_notification(
            tenant=request.tenant,
            phone_e164=phone,
            event_type=event_type,
            message_body=message_body,
        )
        return Response(
            ChannelNotificationSerializer(notification).data,
            status=status.HTTP_201_CREATED,
        )
