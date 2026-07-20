from rest_framework.routers import DefaultRouter

from apps.master_data.views import (
    CustomerViewSet,
    ProviderViewSet,
    ServiceCatalogItemViewSet,
)

router = DefaultRouter()
router.register("providers", ProviderViewSet, basename="providers")
router.register("customers", CustomerViewSet, basename="customers")
router.register("services", ServiceCatalogItemViewSet, basename="services")

urlpatterns = router.urls
