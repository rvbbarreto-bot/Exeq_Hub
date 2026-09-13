from rest_framework import serializers

from apps.nfce.models import NfceInvoice, NfceInvoiceItem
from apps.nfce.services import allowed_actions


class NfceInvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = NfceInvoiceItem
        fields = (
            "id",
            "line_number",
            "product",
            "code",
            "description",
            "ncm",
            "cfop",
            "unit",
            "quantity",
            "unit_price_cents",
            "discount_cents",
            "total_cents",
            "origin",
            "csosn",
            "icms_cst",
            "taxes",
        )


class NfceInvoiceSerializer(serializers.ModelSerializer):
    items = NfceInvoiceItemSerializer(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    artifacts = serializers.SerializerMethodField()

    class Meta:
        model = NfceInvoice
        fields = (
            "id",
            "idempotency_key",
            "status",
            "version",
            "provider",
            "nature_operation",
            "series",
            "number",
            "tp_amb",
            "issue_date",
            "payment_method",
            "payment_amount_cents",
            "discount_cents",
            "total_cents",
            "identification_snapshot",
            "omit_dest",
            "taxes_summary",
            "access_key",
            "protocol",
            "rejection_code",
            "rejection_message",
            "number_consumed",
            "correlation_id",
            "payload_hash",
            "last_validation",
            "items",
            "allowed_actions",
            "artifacts",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_allowed_actions(self, obj: NfceInvoice) -> list[str]:
        return allowed_actions(obj)

    def get_artifacts(self, obj: NfceInvoice) -> dict:
        from apps.nfce.artifacts import has_artifact
        from apps.nfce.models import NfceArtifact
        from apps.nfce.xml_export import resolve_authorized_xml_bytes

        return {
            "xml_authorized": has_artifact(obj, NfceArtifact.Kind.XML_AUTHORIZED)
            or resolve_authorized_xml_bytes(obj) is not None,
            "danfe_pdf": has_artifact(obj, NfceArtifact.Kind.DANFE_PDF),
        }


class NfceDraftCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    provider_id = serializers.UUIDField()
    nature_operation = serializers.CharField(max_length=60, required=False, default="VENDA")
    series = serializers.IntegerField(required=False, default=1, min_value=1)
    tp_amb = serializers.ChoiceField(choices=["1", "2"], required=False)
    issue_date = serializers.DateField(required=False)
    cpf = serializers.CharField(required=False, allow_blank=True, max_length=14)
    omit_dest = serializers.BooleanField(required=False)


class NfceItemsReplaceSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    items = serializers.ListField(child=serializers.DictField(), allow_empty=True)


class NfceEmitSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)


class NfceCancelSerializer(serializers.Serializer):
    justificativa = serializers.CharField(min_length=15, max_length=255)


class NfcePolicyPreviewSerializer(serializers.Serializer):
    provider_id = serializers.UUIDField()
    total_cents = serializers.IntegerField(min_value=0)
    cpf = serializers.CharField(required=False, allow_blank=True, max_length=14)
    cnpj = serializers.CharField(required=False, allow_blank=True, max_length=18)
    delivery = serializers.BooleanField(required=False, default=False)
    installment = serializers.BooleanField(required=False, default=False)


class NfceCheckoutSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    provider_id = serializers.UUIDField()
    items = serializers.ListField(child=serializers.DictField(), min_length=1)
    cpf = serializers.CharField(required=False, allow_blank=True, max_length=14)
    cnpj = serializers.CharField(required=False, allow_blank=True, max_length=18)
    delivery = serializers.BooleanField(required=False, default=False)
    payment_method = serializers.CharField(required=False, allow_blank=True, max_length=2)
    series = serializers.IntegerField(required=False, default=1, min_value=1)
    tp_amb = serializers.ChoiceField(choices=["1", "2"], required=False)
