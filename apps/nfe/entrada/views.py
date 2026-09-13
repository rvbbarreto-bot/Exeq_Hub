"""API REST — NF-e de entrada (Captura Fiscal)."""

from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.master_data.models import Provider
from apps.nfe.entrada.artifacts import read_entrada_xml_bytes
from apps.nfe.entrada.cursor import get_or_create_cursor
from apps.nfe.entrada.exceptions import (
    ManifestationError,
    NfeEntradaDisabledError,
)
from apps.nfe.entrada.feature import nfe_entrada_enabled_for_tenant, require_nfe_entrada_enabled
from apps.nfe.entrada.listing import compute_entrada_kpis, filter_entrada_queryset
from apps.nfe.entrada.models import NfeDistribuicaoCursor, NfeEntradaDocument
from apps.nfe.entrada.serializers import (
    NfeDistribuicaoConfigSerializer,
    NfeDistribuicaoStatusSerializer,
    NfeEntradaDocumentDetailSerializer,
    NfeEntradaDocumentSerializer,
    NfeEntradaManifestRequestSerializer,
    NfeEntradaSyncSerializer,
)
from apps.nfe.entrada.services.distribuicao import schedule_distribuicao_sync
from apps.nfe.entrada.services.manifestacao import manifest_entrada_document
from shared.pagination import HubPageNumberPagination
from shared.storage import StorageError


def _err(exc, http=400):
    return Response(
        {"detail": str(exc), "code": getattr(exc, "code", "nfe_entrada_error")},
        status=http,
    )


def _require_enabled(request):
    if not nfe_entrada_enabled_for_tenant(request.tenant):
        return _err(NfeEntradaDisabledError("NF-e de entrada desabilitada"), 403)
    return None


def _resolve_provider(request, provider_id=None):
    raw = provider_id if provider_id is not None else request.query_params.get("provider_id")
    pid = str(raw).strip() if raw else None
    if pid:
        return get_object_or_404(Provider, pk=pid, tenant=request.tenant)
    provider = (
        Provider.objects.filter(tenant=request.tenant, is_active=True)
        .order_by("legal_name")
        .first()
    )
    if provider is None:
        return None
    return provider


class NfeEntradaListView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        blocked = _require_enabled(request)
        if blocked:
            return blocked
        qs = NfeEntradaDocument.objects.filter(tenant=request.tenant).select_related(
            "provider", "stored_file"
        )
        qs = filter_entrada_queryset(
            qs,
            q=request.query_params.get("q"),
            manifest_status=request.query_params.get("manifest_status"),
            xml_status=request.query_params.get("xml_status"),
            provider_id=request.query_params.get("provider_id"),
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
            days=request.query_params.get("days"),
        ).order_by("-issue_date", "-created_at")
        paginator = HubPageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        data = NfeEntradaDocumentSerializer(page, many=True).data
        payload = paginator.get_paginated_response(data).data
        payload["kpis"] = compute_entrada_kpis(qs)
        return Response(payload)


class NfeEntradaDetailView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request, pk):
        blocked = _require_enabled(request)
        if blocked:
            return blocked
        doc = get_object_or_404(
            NfeEntradaDocument.objects.prefetch_related("manifestations"),
            pk=pk,
            tenant=request.tenant,
        )
        return Response(NfeEntradaDocumentDetailSerializer(doc).data)


class NfeEntradaSyncView(APIView):
    permission_classes = [IsTenantWriter]

    def post(self, request):
        blocked = _require_enabled(request)
        if blocked:
            return blocked
        ser = NfeEntradaSyncSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        provider = _resolve_provider(
            request, provider_id=ser.validated_data.get("provider_id")
        )
        if provider is None:
            return Response(
                {"detail": "Nenhum prestador ativo", "code": "nfe_entrada_provider"},
                status=400,
            )
        require_nfe_entrada_enabled(tenant=request.tenant)
        task_id = schedule_distribuicao_sync(tenant=request.tenant, provider=provider)
        return Response(
            {
                "task_id": task_id,
                "provider_id": str(provider.id),
                "message": "Sync enfileirado",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class NfeEntradaDistributionStatusView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        blocked = _require_enabled(request)
        if blocked:
            return blocked
        provider = _resolve_provider(request)
        if provider is None:
            return Response({"cursors": []})
        cursor = get_or_create_cursor(tenant=request.tenant, provider=provider)
        return Response(NfeDistribuicaoStatusSerializer(cursor).data)


class NfeEntradaDistributionConfigView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        blocked = _require_enabled(request)
        if blocked:
            return blocked
        provider = _resolve_provider(request)
        if provider is None:
            return Response(
                {"detail": "Nenhum prestador ativo", "code": "nfe_entrada_provider"},
                status=400,
            )
        cursor = get_or_create_cursor(tenant=request.tenant, provider=provider)
        return Response(NfeDistribuicaoStatusSerializer(cursor).data)

    def put(self, request):
        blocked = _require_enabled(request)
        if blocked:
            return blocked
        ser = NfeDistribuicaoConfigSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        provider = get_object_or_404(
            Provider, pk=data["provider_id"], tenant=request.tenant
        )
        require_nfe_entrada_enabled(tenant=request.tenant)
        cursor = get_or_create_cursor(tenant=request.tenant, provider=provider)
        updates = []
        if "automatic_enabled" in data:
            cursor.automatic_enabled = data["automatic_enabled"]
            updates.append("automatic_enabled")
        if "interval_seconds" in data:
            cursor.interval_seconds = data["interval_seconds"]
            updates.append("interval_seconds")
        if updates:
            updates.append("updated_at")
            cursor.save(update_fields=updates)
        return Response(NfeDistribuicaoStatusSerializer(cursor).data)


class NfeEntradaManifestView(APIView):
    permission_classes = [IsTenantWriter]

    def post(self, request, pk):
        blocked = _require_enabled(request)
        if blocked:
            return blocked
        doc = get_object_or_404(NfeEntradaDocument, pk=pk, tenant=request.tenant)
        ser = NfeEntradaManifestRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            result = manifest_entrada_document(
                document=doc,
                tp_evento=data["tp_evento"],
                actor_user=request.user,
                actor_ip=request.META.get("REMOTE_ADDR"),
                justificativa=data.get("justificativa") or None,
                confirmed=data.get("confirmed", False),
            )
        except NfeEntradaDisabledError as exc:
            return _err(exc, 403)
        except ManifestationError as exc:
            return _err(exc, 400)
        doc.refresh_from_db(fields=["manifest_status"])
        return Response(
            {
                "success": result.success,
                "idempotent": result.idempotent,
                "c_stat": result.c_stat,
                "protocol": result.protocol,
                "manifestation_id": str(result.manifestation.id),
                "manifest_status": doc.manifest_status,
            },
            status=status.HTTP_200_OK if result.idempotent else status.HTTP_201_CREATED,
        )


class NfeEntradaXmlView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request, pk):
        blocked = _require_enabled(request)
        if blocked:
            return blocked
        doc = get_object_or_404(
            NfeEntradaDocument.objects.select_related("stored_file"),
            pk=pk,
            tenant=request.tenant,
        )
        if doc.xml_status != NfeEntradaDocument.XmlStatus.AVAILABLE:
            return Response(
                {"detail": "XML ainda não disponível", "code": "nfe_entrada_xml_missing"},
                status=404,
            )
        try:
            data = read_entrada_xml_bytes(doc)
        except StorageError as exc:
            return Response(
                {"detail": str(exc), "code": "nfe_entrada_xml_missing"},
                status=404,
            )
        filename = f"entrada-{doc.access_key or doc.id}.xml"
        resp = HttpResponse(data, content_type="application/xml; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        if doc.stored_file_id:
            resp["X-Checksum-SHA256"] = doc.stored_file.checksum_sha256
        return resp
