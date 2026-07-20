from rest_framework import viewsets

from apps.accounts.permissions import IsTenantWriter
from apps.master_data.models import Customer, Provider, ServiceCatalogItem
from apps.master_data.serializers import (
    CustomerSerializer,
    ProviderSerializer,
    ServiceCatalogItemSerializer,
)


class TenantQuerysetMixin:
    def get_queryset(self):
        return self.queryset.filter(tenant=self.request.tenant)


class ProviderViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]


class CustomerViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]


class ServiceCatalogItemViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = ServiceCatalogItem.objects.all()
    serializer_class = ServiceCatalogItemSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]
