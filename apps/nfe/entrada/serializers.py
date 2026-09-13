"""Serializers REST — NF-e de entrada."""

from __future__ import annotations

from rest_framework import serializers

from apps.nfe.entrada.models import (
    NfeDistribuicaoCursor,
    NfeEntradaDocument,
    NfeEntradaManifestation,
)
from integrations.sefaz_nfe.manifestacao.evento import (
    TP_EVENTO_CIENCIA,
    TP_EVENTO_CONFIRMACAO,
    TP_EVENTO_DESCONHECIMENTO,
    TP_EVENTO_NAO_REALIZADA,
)


class NfeEntradaManifestSerializer(serializers.ModelSerializer):
    class Meta:
        model = NfeEntradaManifestation
        fields = (
            "id",
            "tp_evento",
            "n_seq",
            "protocol",
            "c_stat",
            "x_motivo",
            "status",
            "actor_user",
            "correlation_id",
            "created_at",
        )
        read_only_fields = fields


class NfeEntradaDocumentSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.legal_name", read_only=True)
    has_xml = serializers.SerializerMethodField()

    class Meta:
        model = NfeEntradaDocument
        fields = (
            "id",
            "provider",
            "provider_name",
            "nsu",
            "schema_type",
            "access_key",
            "issuer_cnpj",
            "issuer_name",
            "recipient_cnpj",
            "number",
            "series",
            "issue_date",
            "total_cents",
            "nfe_status",
            "xml_status",
            "manifest_status",
            "has_xml",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_has_xml(self, obj: NfeEntradaDocument) -> bool:
        return bool(obj.stored_file_id)


class NfeEntradaDocumentDetailSerializer(NfeEntradaDocumentSerializer):
    manifestations = NfeEntradaManifestSerializer(many=True, read_only=True)
    raw_metadata = serializers.JSONField(read_only=True)

    class Meta(NfeEntradaDocumentSerializer.Meta):
        fields = NfeEntradaDocumentSerializer.Meta.fields + (
            "manifestations",
            "raw_metadata",
            "xml_hash",
        )


class NfeEntradaSyncSerializer(serializers.Serializer):
    provider_id = serializers.UUIDField(required=False, allow_null=True)


class NfeEntradaManifestRequestSerializer(serializers.Serializer):
    tp_evento = serializers.ChoiceField(
        choices=[
            TP_EVENTO_CIENCIA,
            TP_EVENTO_CONFIRMACAO,
            TP_EVENTO_DESCONHECIMENTO,
            TP_EVENTO_NAO_REALIZADA,
        ]
    )
    confirmed = serializers.BooleanField(default=False)
    justificativa = serializers.CharField(required=False, allow_blank=True, max_length=255)


class NfeDistribuicaoConfigSerializer(serializers.Serializer):
    provider_id = serializers.UUIDField()
    automatic_enabled = serializers.BooleanField(required=False)
    interval_seconds = serializers.IntegerField(required=False, min_value=300, max_value=86400)


class NfeDistribuicaoStatusSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.legal_name", read_only=True)
    blocked = serializers.SerializerMethodField()

    class Meta:
        model = NfeDistribuicaoCursor
        fields = (
            "provider",
            "provider_name",
            "cnpj",
            "ult_nsu",
            "max_nsu",
            "last_query_at",
            "last_c_stat",
            "last_x_motivo",
            "blocked_until",
            "blocked",
            "automatic_enabled",
            "interval_seconds",
            "tp_amb",
        )
        read_only_fields = fields

    def get_blocked(self, obj: NfeDistribuicaoCursor) -> bool:
        if obj.blocked_until is None:
            return False
        from django.utils import timezone

        return obj.blocked_until > timezone.now()
