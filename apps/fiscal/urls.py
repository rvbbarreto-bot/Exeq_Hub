from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.fiscal.views import (
    FiscalProfileViewSet,
    MunicipalTaxRuleViewSet,
    TaxResolveView,
    TaxRuleCatalogViewSet,
)

router = DefaultRouter()
router.register("fiscal/profiles", FiscalProfileViewSet, basename="fiscal-profiles")
router.register("fiscal/catalogs", TaxRuleCatalogViewSet, basename="fiscal-catalogs")
router.register("fiscal/rules", MunicipalTaxRuleViewSet, basename="fiscal-rules")

urlpatterns = [
    *router.urls,
    path("tax/resolve", TaxResolveView.as_view(), name="tax-resolve"),
]
