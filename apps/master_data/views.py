from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.master_data.models import Customer, Provider, ServiceCatalogItem
from apps.master_data.serializers import (
    CepLookupSerializer,
    CustomerSerializer,
    DocumentLookupSerializer,
    ProviderSerializer,
    ServiceCatalogItemSerializer,
)
from apps.master_data.services import lookup_cep, lookup_document
from integrations.cadastro.exceptions import (
    CadastroCpfLookupNotSupportedError,
    CadastroDocumentInvalidError,
    CadastroNotFoundError,
    CadastroProviderUnavailableError,
)


class CadastralLookupThrottle(UserRateThrottle):
    scope = "cadastral_lookup"


class TenantQuerysetMixin:
    def get_queryset(self):
        return self.queryset.filter(tenant=self.request.tenant)


class ProviderViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(
        detail=False,
        methods=["post"],
        url_path="lookup-document",
        throttle_classes=[CadastralLookupThrottle],
    )
    def lookup_document_action(self, request):
        return _lookup_response(request, entity_kind="provider")


class CustomerViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(
        detail=False,
        methods=["post"],
        url_path="lookup-document",
        throttle_classes=[CadastralLookupThrottle],
    )
    def lookup_document_action(self, request):
        return _lookup_response(request, entity_kind="customer")


class ServiceCatalogItemViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = ServiceCatalogItem.objects.all()
    serializer_class = ServiceCatalogItemSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]


class ProviderLookupDocumentView(APIView):
    """POST /api/v1/master-data/providers/lookup-document"""

    permission_classes = [IsTenantWriter]
    throttle_classes = [CadastralLookupThrottle]

    def post(self, request):
        return _lookup_response(request, entity_kind="provider")


class CustomerLookupDocumentView(APIView):
    """POST /api/v1/master-data/customers/lookup-document"""

    permission_classes = [IsTenantWriter]
    throttle_classes = [CadastralLookupThrottle]

    def post(self, request):
        return _lookup_response(request, entity_kind="customer")


class CepLookupView(APIView):
    """POST /api/v1/master-data/lookup-cep — autofill de endereço."""

    permission_classes = [IsTenantWriter]
    throttle_classes = [CadastralLookupThrottle]

    def post(self, request):
        ser = CepLookupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = lookup_cep(cep=ser.validated_data["cep"])
        except CadastroDocumentInvalidError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CadastroNotFoundError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_404_NOT_FOUND,
            )
        except CadastroProviderUnavailableError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result.as_api_dict(), status=status.HTTP_200_OK)


def _lookup_response(request, *, entity_kind: str) -> Response:
    ser = DocumentLookupSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    try:
        result = lookup_document(
            tenant=request.tenant,
            document=ser.validated_data["document"],
            entity_kind=entity_kind,
            force=bool(ser.validated_data.get("force")),
            persist_on_existing=bool(ser.validated_data.get("persist")),
        )
    except CadastroDocumentInvalidError as exc:
        return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
    except CadastroCpfLookupNotSupportedError as exc:
        return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
    except CadastroNotFoundError as exc:
        return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_404_NOT_FOUND)
    except CadastroProviderUnavailableError as exc:
        return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(result.as_api_dict(), status=status.HTTP_200_OK)
