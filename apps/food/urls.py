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
    *router.urls,
]
