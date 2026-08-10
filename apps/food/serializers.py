from rest_framework import serializers

from apps.food.exceptions import (
    FoodCustomerNotFoundError,
    FoodError,
    FoodInsufficientStockError,
    FoodInvalidOrderError,
    FoodInvalidTransitionError,
    FoodOrderNotFoundError,
    FoodPaymentError,
    FoodProductNotFoundError,
)
from apps.food.models import FoodCustomer, FoodOrder, FoodOrderLine, FoodProduct
from apps.food.services import (
    create_food_customer,
    create_food_product,
    create_order,
    create_pix_intent_for_order,
)
from decimal import Decimal


def _domain_validation(exc: Exception) -> serializers.ValidationError:
    return serializers.ValidationError(
        {"detail": str(exc), "code": getattr(exc, "code", "food_error")}
    )


class FoodCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodCustomer
        fields = (
            "id",
            "name",
            "phone_e164",
            "email",
            "document",
            "is_active",
            "last_order_at",
            "order_count",
            "total_spent_cents",
            "avg_ticket_cents",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "last_order_at",
            "order_count",
            "total_spent_cents",
            "avg_ticket_cents",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        request = self.context["request"]
        try:
            return create_food_customer(
                tenant=request.tenant,
                name=validated_data["name"],
                phone_e164=validated_data.get("phone_e164") or "",
                email=validated_data.get("email") or "",
                document=validated_data.get("document") or "",
            )
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodProductSerializer(serializers.ModelSerializer):
    initial_stock = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, write_only=True
    )
    min_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, required=False, write_only=True, default=0
    )

    class Meta:
        model = FoodProduct
        fields = (
            "id",
            "sku",
            "name",
            "category",
            "unit",
            "price_cents",
            "cost_cents",
            "is_active",
            "initial_stock",
            "min_quantity",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        request = self.context["request"]
        initial = validated_data.pop("initial_stock", None)
        min_qty = validated_data.pop("min_quantity", 0)
        try:
            return create_food_product(
                tenant=request.tenant,
                sku=validated_data["sku"],
                name=validated_data["name"],
                price_cents=validated_data.get("price_cents", 0),
                cost_cents=validated_data.get("cost_cents", 0),
                category=validated_data.get("category") or "",
                unit=validated_data.get("unit") or "un",
                initial_stock=initial,
                min_quantity=min_qty or 0,
            )
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodOrderLine
        fields = (
            "id",
            "product",
            "sku",
            "name",
            "quantity",
            "unit",
            "unit_price_cents",
            "line_total_cents",
        )
        read_only_fields = fields


class FoodOrderSerializer(serializers.ModelSerializer):
    lines = FoodOrderLineSerializer(many=True, read_only=True)
    pix_copy_paste = serializers.SerializerMethodField()
    charge_id = serializers.UUIDField(read_only=True, allow_null=True)
    charge_status = serializers.SerializerMethodField()

    class Meta:
        model = FoodOrder
        fields = (
            "id",
            "customer",
            "channel",
            "status",
            "payment_status",
            "subtotal_cents",
            "discount_cents",
            "total_cents",
            "notes",
            "idempotency_key",
            "pix_txid",
            "pix_copy_paste",
            "charge_id",
            "charge_status",
            "coupon",
            "fulfillment_mode",
            "delivery_address",
            "marketplace_connection",
            "paid_at",
            "channel_ref",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_pix_copy_paste(self, obj) -> str:
        charge = getattr(obj, "charge", None)
        if charge is None:
            return ""
        return charge.pix_copy_paste or ""

    def get_charge_status(self, obj) -> str:
        charge = getattr(obj, "charge", None)
        if charge is None:
            return ""
        return charge.status or ""


class FoodOrderLineInputSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001")
    )
    unit_price_cents = serializers.IntegerField(required=False, min_value=0)


class FoodOrderCreateSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    channel = serializers.ChoiceField(choices=FoodOrder.Channel.choices)
    lines = FoodOrderLineInputSerializer(many=True)
    idempotency_key = serializers.CharField(min_length=8, max_length=128)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    discount_cents = serializers.IntegerField(required=False, min_value=0, default=0)
    coupon_code = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=64
    )
    fulfillment_mode = serializers.ChoiceField(
        choices=["pickup", "delivery", "counter"],
        required=False,
        default="pickup",
    )
    delivery_address = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    await_pix = serializers.BooleanField(default=True)
    request_pix = serializers.BooleanField(
        default=False,
        help_text="Se true, emite cobrança Pix no gateway na criação do pedido.",
    )

    def create(self, validated_data):
        request = self.context["request"]
        try:
            order = create_order(
                tenant=request.tenant,
                customer_id=validated_data["customer_id"],
                channel=validated_data["channel"],
                lines=validated_data["lines"],
                idempotency_key=validated_data["idempotency_key"],
                notes=validated_data.get("notes") or "",
                discount_cents=validated_data.get("discount_cents") or 0,
                coupon_code=validated_data.get("coupon_code") or "",
                await_pix=validated_data.get("await_pix", True),
            )
            updates = []
            fm = validated_data.get("fulfillment_mode")
            if fm and order.fulfillment_mode != fm:
                order.fulfillment_mode = fm
                updates.append("fulfillment_mode")
            addr = validated_data.get("delivery_address") or ""
            if addr and order.delivery_address != addr:
                order.delivery_address = addr
                updates.append("delivery_address")
            if updates:
                updates.append("updated_at")
                order.save(update_fields=updates)
            if validated_data.get("request_pix") and order.payment_status != (
                FoodOrder.PaymentStatus.PAID
            ):
                order = create_pix_intent_for_order(
                    tenant=request.tenant, order_id=order.id
                )
            return order
        except (
            FoodCustomerNotFoundError,
            FoodProductNotFoundError,
            FoodInsufficientStockError,
            FoodInvalidOrderError,
            FoodInvalidTransitionError,
            FoodPaymentError,
            FoodOrderNotFoundError,
            FoodError,
        ) as exc:
            raise _domain_validation(exc) from exc


class FoodCouponSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodCoupon

        model = FoodCoupon
        fields = (
            "id",
            "campaign",
            "code",
            "discount_type",
            "percent_bps",
            "amount_cents",
            "min_order_cents",
            "max_redemptions",
            "redemption_count",
            "valid_from",
            "valid_until",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "redemption_count", "created_at", "updated_at")


class FoodCouponCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    discount_type = serializers.ChoiceField(choices=["percent", "fixed_cents"])
    percent_bps = serializers.IntegerField(required=False, min_value=0, default=0)
    amount_cents = serializers.IntegerField(required=False, min_value=0, default=0)
    campaign_id = serializers.UUIDField(required=False, allow_null=True)
    min_order_cents = serializers.IntegerField(required=False, min_value=0, default=0)
    max_redemptions = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )

    def create(self, validated_data):
        from apps.food.models import FoodCampaign
        from apps.food.retention import create_coupon

        request = self.context["request"]
        campaign = None
        cid = validated_data.get("campaign_id")
        if cid:
            campaign = FoodCampaign.objects.filter(
                tenant=request.tenant, pk=cid
            ).first()
        try:
            return create_coupon(
                tenant=request.tenant,
                code=validated_data["code"],
                discount_type=validated_data["discount_type"],
                percent_bps=validated_data.get("percent_bps") or 0,
                amount_cents=validated_data.get("amount_cents") or 0,
                campaign=campaign,
                min_order_cents=validated_data.get("min_order_cents") or 0,
                max_redemptions=validated_data.get("max_redemptions"),
            )
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodRetentionStepInputSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=1)
    delay_days = serializers.IntegerField(min_value=0, default=0)
    message_template = serializers.CharField()
    channel = serializers.ChoiceField(choices=["whatsapp"], default="whatsapp")
    coupon_id = serializers.UUIDField(required=False, allow_null=True)


class FoodRetentionRuleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    kind = serializers.ChoiceField(
        choices=["inactivity", "vip", "high_ticket", "custom"]
    )
    inactivity_days = serializers.IntegerField(min_value=1, default=30)
    min_order_count = serializers.IntegerField(min_value=0, default=0)
    min_avg_ticket_cents = serializers.IntegerField(min_value=0, default=0)
    steps = FoodRetentionStepInputSerializer(many=True)

    def create(self, validated_data):
        from apps.food.retention import create_retention_rule

        request = self.context["request"]
        try:
            return create_retention_rule(
                tenant=request.tenant,
                name=validated_data["name"],
                kind=validated_data["kind"],
                steps=validated_data["steps"],
                inactivity_days=validated_data.get("inactivity_days") or 30,
                min_order_count=validated_data.get("min_order_count") or 0,
                min_avg_ticket_cents=validated_data.get("min_avg_ticket_cents") or 0,
            )
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodRetentionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodRetentionRule

        model = FoodRetentionRule
        fields = (
            "id",
            "name",
            "kind",
            "is_active",
            "inactivity_days",
            "min_order_count",
            "min_avg_ticket_cents",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

class FoodSupplierSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodSupplier

        model = FoodSupplier
        fields = (
            "id",
            "name",
            "document",
            "phone",
            "email",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        from apps.food.operations import create_supplier

        request = self.context["request"]
        try:
            return create_supplier(tenant=request.tenant, **validated_data)
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodPurchaseLineSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodPurchaseLine

        model = FoodPurchaseLine
        fields = (
            "id",
            "product",
            "quantity",
            "unit_cost_cents",
            "line_total_cents",
        )
        read_only_fields = fields


class FoodPurchaseSerializer(serializers.ModelSerializer):
    lines = FoodPurchaseLineSerializer(many=True, read_only=True)

    class Meta:
        from apps.food.models import FoodPurchase

        model = FoodPurchase
        fields = (
            "id",
            "supplier",
            "status",
            "idempotency_key",
            "expected_at",
            "received_at",
            "notes",
            "total_cents",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FoodPurchaseCreateSerializer(serializers.Serializer):
    supplier_id = serializers.UUIDField()
    lines = serializers.ListField(child=serializers.DictField(), min_length=1)
    idempotency_key = serializers.CharField(min_length=8, max_length=128)
    expected_at = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    mark_ordered = serializers.BooleanField(default=True)

    def create(self, validated_data):
        from apps.food.operations import create_purchase

        request = self.context["request"]
        try:
            return create_purchase(tenant=request.tenant, **validated_data)
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodDeliveryRouteSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodDeliveryRoute

        model = FoodDeliveryRoute
        fields = (
            "id",
            "name",
            "service_date",
            "driver_name",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "status", "created_at", "updated_at")

    def create(self, validated_data):
        from apps.food.operations import create_delivery_route

        request = self.context["request"]
        return create_delivery_route(tenant=request.tenant, **validated_data)


class FoodDeliveryStopSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodDeliveryStop

        model = FoodDeliveryStop
        fields = (
            "id",
            "route",
            "order",
            "sequence",
            "status",
            "delivered_at",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FoodMarketplaceConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodMarketplaceConnection

        model = FoodMarketplaceConnection
        fields = (
            "id",
            "provider",
            "merchant_ref",
            "is_active",
            "settings",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data):
        from apps.food.operations import upsert_marketplace_connection

        request = self.context["request"]
        try:
            return upsert_marketplace_connection(
                tenant=request.tenant, **validated_data
            )
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class MarketplaceImportSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=["ifood", "aiqfome"])
    external_order_id = serializers.CharField(max_length=128)
    customer_name = serializers.CharField(max_length=255)
    customer_phone = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=32
    )
    lines = serializers.ListField(child=serializers.DictField(), min_length=1)
    total_cents = serializers.IntegerField(required=False, min_value=0)
    delivery_address = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    merchant_ref = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=128
    )
    paid = serializers.BooleanField(default=True)

    def create(self, validated_data):
        from apps.food.operations import import_marketplace_order

        request = self.context["request"]
        try:
            return import_marketplace_order(tenant=request.tenant, **validated_data)
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodBomComponentSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodBomComponent

        model = FoodBomComponent
        fields = ("id", "product", "quantity_per_unit", "scrap_bps")
        read_only_fields = fields


class FoodBomSerializer(serializers.ModelSerializer):
    components = FoodBomComponentSerializer(many=True, read_only=True)

    class Meta:
        from apps.food.models import FoodBom

        model = FoodBom
        fields = (
            "id",
            "product",
            "name",
            "is_active",
            "expected_yield_bps",
            "components",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FoodBomCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    expected_yield_bps = serializers.IntegerField(
        required=False, min_value=1, max_value=10000, default=10000
    )
    components = serializers.ListField(child=serializers.DictField(), min_length=1)

    def create(self, validated_data):
        from apps.food.production import create_bom

        request = self.context["request"]
        try:
            return create_bom(tenant=request.tenant, **validated_data)
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodCapacitySlotSerializer(serializers.ModelSerializer):
    free_units = serializers.IntegerField(read_only=True)

    class Meta:
        from apps.food.models import FoodCapacitySlot

        model = FoodCapacitySlot
        fields = (
            "id",
            "service_date",
            "starts_at",
            "ends_at",
            "name",
            "capacity_units",
            "booked_units",
            "free_units",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "booked_units", "created_at", "updated_at", "free_units")

    def create(self, validated_data):
        from apps.food.production import create_capacity_slot

        request = self.context["request"]
        try:
            return create_capacity_slot(tenant=request.tenant, **validated_data)
        except FoodError as exc:
            raise _domain_validation(exc) from exc


class FoodProductionOrderSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.food.models import FoodProductionOrder

        model = FoodProductionOrder
        fields = (
            "id",
            "product",
            "bom",
            "capacity_slot",
            "status",
            "quantity_planned",
            "quantity_produced",
            "loss_quantity",
            "yield_bps",
            "idempotency_key",
            "notes",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FoodProductionOrderCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity_planned = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    idempotency_key = serializers.CharField(min_length=8, max_length=128)
    bom_id = serializers.UUIDField(required=False, allow_null=True)
    capacity_slot_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def create(self, validated_data):
        from apps.food.production import create_production_order

        request = self.context["request"]
        try:
            return create_production_order(tenant=request.tenant, **validated_data)
        except FoodError as exc:
            raise _domain_validation(exc) from exc
