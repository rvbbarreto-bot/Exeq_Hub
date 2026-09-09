from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.food.views import (
    FoodBomViewSet,
    FoodCapacitySlotViewSet,
    FoodCouponViewSet,
    FoodCustomerViewSet,
    FoodDashboardView,
    FoodDeliveryRouteViewSet,
    FoodDeliveryStopViewSet,
    FoodIntelligenceView,
    FoodMarketplaceConnectionViewSet,
    FoodMarketplaceImportView,
    FoodMarketplaceSyncView,
    FoodMrpView,
    FoodOrderViewSet,
    FoodProductViewSet,
    FoodProductionOrderViewSet,
    FoodPurchaseViewSet,
    FoodRetentionRuleViewSet,
    FoodSupplierViewSet,
)
from apps.food.fiscal_views import (
    FoodIfoodEmitBatchView,
    FoodIfoodFiscalDetailView,
    FoodIfoodFiscalIgnoreView,
    FoodIfoodFiscalListView,
)
from apps.food.webhook_views import MercadoPagoFoodWebhookView

router = DefaultRouter()
router.register("food/customers", FoodCustomerViewSet, basename="food-customers")
router.register("food/products", FoodProductViewSet, basename="food-products")
router.register("food/orders", FoodOrderViewSet, basename="food-orders")
router.register("food/coupons", FoodCouponViewSet, basename="food-coupons")
router.register(
    "food/retention-rules", FoodRetentionRuleViewSet, basename="food-retention-rules"
)
router.register("food/suppliers", FoodSupplierViewSet, basename="food-suppliers")
router.register("food/purchases", FoodPurchaseViewSet, basename="food-purchases")
router.register(
    "food/delivery-routes", FoodDeliveryRouteViewSet, basename="food-delivery-routes"
)
router.register(
    "food/delivery-stops", FoodDeliveryStopViewSet, basename="food-delivery-stops"
)
router.register(
    "food/marketplace-connections",
    FoodMarketplaceConnectionViewSet,
    basename="food-marketplace-connections",
)
router.register("food/boms", FoodBomViewSet, basename="food-boms")
router.register(
    "food/capacity-slots", FoodCapacitySlotViewSet, basename="food-capacity-slots"
)
router.register(
    "food/production-orders",
    FoodProductionOrderViewSet,
    basename="food-production-orders",
)

urlpatterns = [
    path("food/dashboard", FoodDashboardView.as_view(), name="food-dashboard"),
    path("food/mrp", FoodMrpView.as_view(), name="food-mrp"),
    path(
        "food/intelligence",
        FoodIntelligenceView.as_view(),
        name="food-intelligence",
    ),
    path(
        "food/marketplace/import",
        FoodMarketplaceImportView.as_view(),
        name="food-marketplace-import",
    ),
    path(
        "food/marketplace/sync",
        FoodMarketplaceSyncView.as_view(),
        name="food-marketplace-sync",
    ),
    path(
        "food/webhooks/mercadopago",
        MercadoPagoFoodWebhookView.as_view(),
        name="food-webhooks-mercadopago",
    ),
    path(
        "food/ifood/fiscal/",
        FoodIfoodFiscalListView.as_view(),
        name="food-ifood-fiscal-list",
    ),
    path(
        "food/ifood/fiscal/<uuid:order_id>/",
        FoodIfoodFiscalDetailView.as_view(),
        name="food-ifood-fiscal-detail",
    ),
    path(
        "food/ifood/fiscal/<uuid:order_id>/ignore/",
        FoodIfoodFiscalIgnoreView.as_view(),
        name="food-ifood-fiscal-ignore",
    ),
    path(
        "food/ifood/emit-batch/",
        FoodIfoodEmitBatchView.as_view(),
        name="food-ifood-emit-batch",
    ),
    *router.urls,
]
