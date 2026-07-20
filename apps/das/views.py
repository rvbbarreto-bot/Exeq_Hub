from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import IsTenantWriter
from apps.das.models import GuiaFiscal
from apps.das.serializers import GuiaFiscalCreateSerializer, GuiaFiscalSerializer


class GuiaFiscalViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = GuiaFiscal.objects.filter(tenant=self.request.tenant).order_by(
            "-competencia",
            "-created_at",
        )
        status_filter = self.request.query_params.get("status")
        tipo = self.request.query_params.get("tipo_guia")
        provider = self.request.query_params.get("provider")
        competencia = self.request.query_params.get("competencia")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if tipo:
            qs = qs.filter(tipo_guia=tipo)
        if provider:
            qs = qs.filter(provider_id=provider)
        if competencia:
            qs = qs.filter(competencia=competencia)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return GuiaFiscalCreateSerializer
        return GuiaFiscalSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guia = serializer.save()
        return Response(GuiaFiscalSerializer(guia).data, status=status.HTTP_201_CREATED)
