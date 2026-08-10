from django.contrib import admin

from apps.food.models import (
    FoodBom,
    FoodBomComponent,
    FoodCampaign,
    FoodCapacitySlot,
    FoodCoupon,
    FoodCouponRedemption,
    FoodCustomer,
    FoodDeliveryRoute,
    FoodDeliveryStop,
    FoodMarketplaceConnection,
    FoodOrder,
    FoodOrderLine,
    FoodProduct,
    FoodProductionOrder,
    FoodPurchase,
    FoodPurchaseLine,
    FoodRetentionDispatch,
    FoodRetentionEnrollment,
    FoodRetentionRule,
    FoodRetentionStep,
    FoodStockBalance,
    FoodStockMovement,
    FoodSupplier,
)
from shared.money import format_brl_from_cents


class FoodAdminMixin:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "tenant":
            kwargs["label"] = "Empresa"
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Empresa", ordering="tenant")
    def empresa(self, obj):
        return obj.tenant


def _cents_display(description: str, attr: str):
    @admin.display(description=description, ordering=attr)
    def _display(self, obj):
        if obj is None:
            return "—"
        return format_brl_from_cents(getattr(obj, attr, None))

    _display.__name__ = f"{attr}_brl"
    return _display


class FoodOrderLineInline(admin.TabularInline):
    model = FoodOrderLine
    extra = 0
    readonly_fields = (
        "sku",
        "name",
        "quantity",
        "unit",
        "unit_price_cents",
        "line_total_cents",
        "product",
    )
    can_delete = False


@admin.register(FoodCustomer)
class FoodCustomerAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "phone_e164",
        "is_active",
        "order_count",
        "avg_ticket_brl",
        "last_order_at",
        "empresa",
    )
    search_fields = ("name", "phone_e164", "document")
    list_filter = ("is_active",)
    avg_ticket_brl = _cents_display("Ticket médio", "avg_ticket_cents")


@admin.register(FoodProduct)
class FoodProductAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "category",
        "unit",
        "price_brl",
        "is_active",
        "empresa",
    )
    search_fields = ("sku", "name", "category")
    list_filter = ("is_active", "category")
    price_brl = _cents_display("Preço", "price_cents")


@admin.register(FoodOrder)
class FoodOrderAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "channel",
        "status",
        "payment_status",
        "total_brl",
        "charge",
        "created_at",
        "empresa",
    )
    list_filter = ("channel", "status", "payment_status")
    search_fields = ("idempotency_key", "pix_txid", "customer__name", "customer__phone_e164")
    raw_id_fields = ("charge", "customer", "coupon")
    inlines = [FoodOrderLineInline]
    readonly_fields = ("subtotal_cents", "total_cents", "paid_at")
    total_brl = _cents_display("Total", "total_cents")


@admin.register(FoodCampaign)
class FoodCampaignAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "empresa")
    search_fields = ("name", "code")
    list_filter = ("is_active",)


@admin.register(FoodCoupon)
class FoodCouponAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "discount_type",
        "percent_bps",
        "amount_cents",
        "redemption_count",
        "is_active",
        "empresa",
    )
    search_fields = ("code",)
    list_filter = ("discount_type", "is_active")


@admin.register(FoodCouponRedemption)
class FoodCouponRedemptionAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("coupon", "order", "customer", "discount_cents", "empresa")
    raw_id_fields = ("coupon", "order", "customer", "campaign")


class FoodRetentionStepInline(admin.TabularInline):
    model = FoodRetentionStep
    extra = 0


@admin.register(FoodRetentionRule)
class FoodRetentionRuleAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("name", "kind", "is_active", "inactivity_days", "empresa")
    list_filter = ("kind", "is_active")
    inlines = [FoodRetentionStepInline]


@admin.register(FoodRetentionEnrollment)
class FoodRetentionEnrollmentAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "customer",
        "rule",
        "status",
        "next_sequence",
        "next_fire_at",
        "empresa",
    )
    list_filter = ("status",)
    raw_id_fields = ("customer", "rule")


@admin.register(FoodRetentionDispatch)
class FoodRetentionDispatchAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("idempotency_key", "status", "fired_at", "empresa")
    list_filter = ("status",)
    raw_id_fields = ("enrollment", "step", "channel_notification")


@admin.register(FoodSupplier)
class FoodSupplierAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("name", "document", "is_active", "empresa")
    search_fields = ("name", "document")


class FoodPurchaseLineInline(admin.TabularInline):
    model = FoodPurchaseLine
    extra = 0


@admin.register(FoodPurchase)
class FoodPurchaseAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("id", "supplier", "status", "total_cents", "received_at", "empresa")
    list_filter = ("status",)
    inlines = [FoodPurchaseLineInline]
    raw_id_fields = ("supplier",)


@admin.register(FoodDeliveryRoute)
class FoodDeliveryRouteAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("name", "service_date", "driver_name", "status", "empresa")
    list_filter = ("status",)


@admin.register(FoodDeliveryStop)
class FoodDeliveryStopAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("route", "order", "sequence", "status", "empresa")
    list_filter = ("status",)
    raw_id_fields = ("route", "order")


@admin.register(FoodMarketplaceConnection)
class FoodMarketplaceConnectionAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("provider", "merchant_ref", "is_active", "empresa")
    list_filter = ("provider", "is_active")


class FoodBomComponentInline(admin.TabularInline):
    model = FoodBomComponent
    extra = 0


@admin.register(FoodBom)
class FoodBomAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = ("name", "product", "is_active", "expected_yield_bps", "empresa")
    list_filter = ("is_active",)
    inlines = [FoodBomComponentInline]
    raw_id_fields = ("product",)


@admin.register(FoodCapacitySlot)
class FoodCapacitySlotAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "service_date",
        "starts_at",
        "ends_at",
        "capacity_units",
        "booked_units",
        "empresa",
    )


@admin.register(FoodProductionOrder)
class FoodProductionOrderAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "status",
        "quantity_planned",
        "quantity_produced",
        "yield_bps",
        "empresa",
    )
    list_filter = ("status",)
    raw_id_fields = ("product", "bom", "capacity_slot")


@admin.register(FoodStockBalance)
class FoodStockBalanceAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "product",
        "quantity",
        "reserved_quantity",
        "min_quantity",
        "empresa",
    )
    search_fields = ("product__sku", "product__name")


@admin.register(FoodStockMovement)
class FoodStockMovementAdmin(FoodAdminMixin, admin.ModelAdmin):
    list_display = (
        "product",
        "movement_type",
        "quantity",
        "balance_after",
        "reason",
        "created_at",
        "empresa",
    )
    list_filter = ("movement_type",)
    search_fields = ("product__sku", "reason")
