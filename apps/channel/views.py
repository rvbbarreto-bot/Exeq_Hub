from rest_framework import serializers, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Tenant
from apps.accounts.permissions import IsTenantWriter
from apps.channel.models import ChannelNotification, ChannelSession
from apps.channel.services import enqueue_notification, ingest_inbound_message


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
            "provider_ref",
            "created_at",
        )
        read_only_fields = fields


class ChannelSessionViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsTenantWriter]
    serializer_class = ChannelSessionSerializer

    def get_queryset(self):
        return ChannelSession.objects.filter(tenant=self.request.tenant)


class EvolutionWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        tenant_slug = payload.get("tenant_slug")
        phone = payload.get("phone_e164")
        message_id = payload.get("message_id")
        text = payload.get("text", "")
        if not all([tenant_slug, phone, message_id]):
            return Response({"detail": "payload incompleto"}, status=400)
        try:
            tenant = Tenant.objects.get(slug=tenant_slug, status=Tenant.Status.ACTIVE)
        except Tenant.DoesNotExist:
            return Response({"detail": "tenant inválido"}, status=400)
        session = ingest_inbound_message(
            tenant=tenant,
            phone_e164=phone,
            message_id=message_id,
            text=text,
        )
        return Response(ChannelSessionSerializer(session).data, status=200)


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
