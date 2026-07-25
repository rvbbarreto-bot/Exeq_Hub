from io import BytesIO

from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsTenantWriter
from apps.das.models import GuiaFiscal
from apps.das.serializers import GuiaFiscalCreateSerializer, GuiaFiscalSerializer
from shared.storage import StorageError, get_storage


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

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """Stream do PDF da guia (StoredFile persistido na emissão)."""
        guia = self.get_object()
        if not guia.pdf_file_id:
            return Response(
                {"detail": "PDF indisponível", "code": "das_pdf_missing"},
                status=404,
            )
        stored = guia.pdf_file
        try:
            data = get_storage().get(key=stored.object_key)
        except StorageError as exc:
            return Response({"detail": str(exc)}, status=404)
        filename = f"guia-{guia.tipo_guia}-{guia.competencia}-{guia.id}.pdf"
        return FileResponse(
            BytesIO(data),
            as_attachment=True,
            filename=filename,
            content_type=stored.content_type or "application/pdf",
        )
