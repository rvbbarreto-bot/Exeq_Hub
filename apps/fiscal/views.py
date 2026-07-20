from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.fiscal.exceptions import (
    CatalogNotEditableError,
    PublishChecklistIncompleteError,
    TaxRuleNotFoundError,
)
from apps.fiscal.models import FiscalProfile, MunicipalTaxRule, TaxRuleCatalog
from apps.fiscal.serializers import (
    FiscalProfileSerializer,
    MunicipalTaxRuleSerializer,
    TaxResolveSerializer,
    TaxRuleCatalogSerializer,
)
from apps.fiscal.tax_engine import publish_catalog, resolve_tax_rule, rule_to_payload


class TenantQuerysetMixin:
    def get_queryset(self):
        return self.queryset.filter(tenant=self.request.tenant)


class FiscalProfileViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = FiscalProfile.objects.all()
    serializer_class = FiscalProfileSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]


class TaxRuleCatalogViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = TaxRuleCatalog.objects.all()
    serializer_class = TaxRuleCatalogSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def partial_update(self, request, *args, **kwargs):
        catalog = self.get_object()
        if "publish_checklist" in request.data:
            try:
                from apps.fiscal.tax_engine import assert_catalog_editable

                assert_catalog_editable(catalog)
            except CatalogNotEditableError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            catalog.publish_checklist = {
                **(catalog.publish_checklist or {}),
                **request.data["publish_checklist"],
            }
            catalog.save(update_fields=["publish_checklist", "updated_at"])
            return Response(self.get_serializer(catalog).data)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        catalog = self.get_object()
        try:
            published = publish_catalog(catalog)
        except PublishChecklistIncompleteError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code, "missing": exc.missing},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CatalogNotEditableError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(published).data)


class MunicipalTaxRuleViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = MunicipalTaxRule.objects.select_related("catalog", "fiscal_profile")
    serializer_class = MunicipalTaxRuleSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "head", "options"]


class TaxResolveView(APIView):
    permission_classes = [IsTenantWriter]

    def post(self, request):
        serializer = TaxResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            profile = FiscalProfile.objects.get(
                id=data["fiscal_profile_id"],
                tenant=request.tenant,
            )
        except FiscalProfile.DoesNotExist:
            return Response({"detail": "Perfil fiscal não encontrado"}, status=404)
        try:
            rule = resolve_tax_rule(
                tenant=request.tenant,
                fiscal_profile=profile,
                ibge_code=data["ibge_code"],
                service_code=data["service_code"],
                tax_regime=data["tax_regime"],
                competence_date=data["competence_date"],
            )
        except TaxRuleNotFoundError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(rule_to_payload(rule))
