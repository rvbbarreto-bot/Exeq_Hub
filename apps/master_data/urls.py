from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.master_data.views import (
    CepLookupView,
    CustomerLookupDocumentView,
    CustomerViewSet,
    NbsSearchView,
    ProviderLookupDocumentView,
    ProviderViewSet,
    ServiceCatalogItemViewSet,
)

router = DefaultRouter()
router.register("providers", ProviderViewSet, basename="providers")
router.register("customers", CustomerViewSet, basename="customers")
router.register("services", ServiceCatalogItemViewSet, basename="services")

urlpatterns = [
    path(
        "master-data/providers/lookup-document",
        ProviderLookupDocumentView.as_view(),
        name="master-data-provider-lookup",
    ),
    path(
        "master-data/customers/lookup-document",
        CustomerLookupDocumentView.as_view(),
        name="master-data-customer-lookup",
    ),
    path(
        "master-data/lookup-cep",
        CepLookupView.as_view(),
        name="master-data-lookup-cep",
    ),
    path(
        "master-data/nbs/search",
        NbsSearchView.as_view(),
        name="master-data-nbs-search",
    ),
    *router.urls,
]
