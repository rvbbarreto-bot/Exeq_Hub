from rest_framework import serializers

from apps.nfe.models import NfeInvoice, NfeInvoiceItem, NfeProduct
from apps.nfe.services import allowed_actions


class NfeProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = NfeProduct
        fields = (
            "id",
            "code",
            "description",
            "unit",
            "unit_price_cents",
            "ncm",
            "origin",
            "cfop_internal",
            "cfop_interstate",
            "csosn",
            "icms_cst",
            "icms_rate_bp",
            "pis_cst",
            "pis_rate_bp",
            "cofins_cst",
            "cofins_rate_bp",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class NfeInvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = NfeInvoiceItem
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


class NfeInvoiceSerializer(serializers.ModelSerializer):
    items = NfeInvoiceItemSerializer(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    artifacts = serializers.SerializerMethodField()

    class Meta:
        model = NfeInvoice
        fields = (
            "id",
            "idempotency_key",
            "status",
            "version",
            "provider",
            "customer",
            "nature_operation",
            "finality",
            "consumer_final",
            "buyer_presence",
            "ind_ie_dest",
            "series",
            "number",
            "tp_amb",
            "issue_date",
            "freight_mod",
            "freight_cents",
            "discount_cents",
            "payment_method",
            "payment_amount_cents",
            "total_cents",
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

    def get_allowed_actions(self, obj: NfeInvoice) -> list[str]:
        return allowed_actions(obj)

    def get_artifacts(self, obj: NfeInvoice) -> dict:
        from apps.nfe.artifacts import has_danfe_pdf, has_xml_authorized, has_xml_cce

        return {
            "xml_authorized": has_xml_authorized(obj),
            "danfe_pdf": has_danfe_pdf(obj),
            "xml_cce": has_xml_cce(obj),
        }


class NfeDraftCreateSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
    provider_id = serializers.UUIDField()
    customer_id = serializers.UUIDField()
    nature_operation = serializers.CharField(max_length=60, required=False, default="VENDA")
    series = serializers.IntegerField(required=False, default=1, min_value=1)
    tp_amb = serializers.ChoiceField(choices=["1", "2"], required=False)
    ind_ie_dest = serializers.ChoiceField(choices=["1", "2", "9"], required=False, default="9")
    issue_date = serializers.DateField(required=False)


class NfeItemsReplaceSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    items = serializers.ListField(child=serializers.DictField(), allow_empty=True)


class NfeEmitSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)


class NfeCancelSerializer(serializers.Serializer):
    justificativa = serializers.CharField(min_length=15, max_length=255)


class NfeCceSerializer(serializers.Serializer):
    x_correcao = serializers.CharField(min_length=15, max_length=1000)


class NfeConfigSeriesSerializer(serializers.Serializer):
    provider_id = serializers.UUIDField()
    series = serializers.IntegerField(required=False, default=1, min_value=1)
    tp_amb = serializers.ChoiceField(choices=["1", "2"], required=False)
    next_number = serializers.IntegerField(required=False, min_value=1)
    is_active = serializers.BooleanField(required=False, default=True)


class NfeInutilizationSerializer(serializers.Serializer):
    provider_id = serializers.UUIDField()
    series = serializers.IntegerField(required=False, default=1, min_value=1)
    tp_amb = serializers.ChoiceField(choices=["1", "2"], required=False)
    n_ini = serializers.IntegerField(min_value=1)
    n_fin = serializers.IntegerField(min_value=1)
    x_just = serializers.CharField(min_length=15, max_length=255)
    ano = serializers.CharField(required=False, allow_blank=True, max_length=4)


class NfeResendEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)


class NfeCloneSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=128)
