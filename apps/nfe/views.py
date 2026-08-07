from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.master_data.models import Customer, Provider
from apps.nfe.artifacts import (
    get_artifact,
    has_danfe_pdf,
    read_artifact_bytes,
)
from apps.nfe.exceptions import (
    NfeDisabledError,
    NfeGateError,
    NfeInvalidTransitionError,
    NfeValidationError,
    NfeVersionConflictError,
)
from apps.nfe.gate import build_config_payload, build_gate_payload, upsert_number_series
from apps.nfe.models import NfeArtifact, NfeInvoice, NfeProduct
from apps.nfe.serializers import (
    NfeCancelSerializer,
    NfeCloneSerializer,
    NfeConfigSeriesSerializer,
    NfeDraftCreateSerializer,
    NfeEmitSerializer,
    NfeInvoiceSerializer,
    NfeItemsReplaceSerializer,
    NfeProductSerializer,
)
from apps.nfe.services import (
    cancel_invoice,
    clone_invoice,
    create_draft,
    discard_draft,
    emit_invoice,
    nfe_feature_enabled,
    replace_items,
    validate_invoice,
)
from shared.pagination import HubPageNumberPagination


def _err(exc, http=400):
    return Response({"detail": str(exc), "code": getattr(exc, "code", "nfe_error")}, status=http)


class NfeGateView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        provider_id = (request.query_params.get("provider_id") or "").strip() or None
        series = request.query_params.get("series")
        tp_amb = (request.query_params.get("tp_amb") or "").strip() or None
        try:
            ser = int(series) if series not in (None, "") else None
        except (TypeError, ValueError):
            return Response(
                {"detail": "series inválida", "code": "nfe_gate"},
                status=400,
            )
        return Response(
            build_gate_payload(
                tenant=request.tenant,
                provider_id=provider_id,
                series=ser,
                tp_amb=tp_amb,
            )
        )


class NfeConfigView(APIView):
    """GET/PUT /nfe/config/ — série, ambiente, próximo nº (T6)."""

    permission_classes = [IsTenantWriter]

    def get(self, request):
        provider_id = (request.query_params.get("provider_id") or "").strip() or None
        return Response(
            build_config_payload(tenant=request.tenant, provider_id=provider_id)
        )

    def put(self, request):
        if not nfe_feature_enabled():
            return _err(NfeDisabledError("NF-e desabilitada"), 403)
        ser = NfeConfigSeriesSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        provider = get_object_or_404(
            Provider, pk=data["provider_id"], tenant=request.tenant
        )
        try:
            row = upsert_number_series(
                tenant=request.tenant,
                provider=provider,
                series=data.get("series") or 1,
                tp_amb=data.get("tp_amb"),
                next_number=data.get("next_number"),
                is_active=data.get("is_active", True),
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc), "code": "nfe_config"},
                status=400,
            )
        return Response(
            {
                "series": {
                    "id": str(row.id),
                    "provider_id": str(row.provider_id),
                    "series": row.series,
                    "tp_amb": row.tp_amb,
                    "next_number": row.next_number,
                    "is_active": row.is_active,
                },
                "config": build_config_payload(
                    tenant=request.tenant, provider_id=str(provider.id)
                ),
            }
        )


class NfeProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTenantWriter]
    serializer_class = NfeProductSerializer
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return NfeProduct.objects.filter(tenant=self.request.tenant).order_by("code")

    def create(self, request, *args, **kwargs):
        if not nfe_feature_enabled():
            return _err(NfeDisabledError("NF-e desabilitada"), 403)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=request.tenant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        if not nfe_feature_enabled():
            return _err(NfeDisabledError("NF-e desabilitada"), 403)
        return super().partial_update(request, *args, **kwargs)


class NfeInvoiceViewSet(viewsets.ViewSet):
    permission_classes = [IsTenantWriter]

    def list(self, request):
        qs = NfeInvoice.objects.filter(tenant=request.tenant).order_by("-created_at")
        status_f = (request.query_params.get("status") or "").strip().lower()
        if status_f and status_f != "all":
            qs = qs.filter(status=status_f)
        page = HubPageNumberPagination()
        result = page.paginate_queryset(qs, request)
        ser = NfeInvoiceSerializer(result, many=True)
        return page.get_paginated_response(ser.data)

    def retrieve(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        return Response(NfeInvoiceSerializer(inv).data)

    def create(self, request):
        ser = NfeDraftCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            provider = get_object_or_404(
                Provider, pk=data["provider_id"], tenant=request.tenant
            )
            customer = get_object_or_404(
                Customer, pk=data["customer_id"], tenant=request.tenant
            )
            inv = create_draft(
                tenant=request.tenant,
                provider=provider,
                customer=customer,
                idempotency_key=data["idempotency_key"],
                nature_operation=data.get("nature_operation") or "VENDA",
                series=data.get("series") or 1,
                tp_amb=data.get("tp_amb"),
                ind_ie_dest=data.get("ind_ie_dest") or "9",
                issue_date=data.get("issue_date"),
                actor=getattr(request.user, "email", "api") or "api",
            )
        except (NfeDisabledError, NfeGateError) as exc:
            return _err(exc, 403 if isinstance(exc, NfeDisabledError) else 400)
        return Response(NfeInvoiceSerializer(inv).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["put"], url_path="items")
    def items(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        ser = NfeItemsReplaceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            replace_items(
                inv,
                items=ser.validated_data["items"],
                expected_version=ser.validated_data.get("version"),
            )
            inv.refresh_from_db()
        except NfeVersionConflictError as exc:
            return _err(exc, 409)
        except NfeDisabledError as exc:
            return _err(exc, 403)
        except NfeInvalidTransitionError as exc:
            return _err(exc, 400)
        return Response(NfeInvoiceSerializer(inv).data)

    @action(detail=True, methods=["post"], url_path="validate")
    def validate(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        try:
            result = validate_invoice(inv)
            inv.refresh_from_db()
        except NfeDisabledError as exc:
            return _err(exc, 403)
        return Response({"validation": result, "invoice": NfeInvoiceSerializer(inv).data})

    @action(detail=True, methods=["post"], url_path="emit")
    def emit(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        ser = NfeEmitSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        try:
            emit_invoice(
                inv,
                expected_version=ser.validated_data.get("version"),
                actor=getattr(request.user, "email", "api") or "api",
            )
            inv.refresh_from_db()
        except NfeVersionConflictError as exc:
            return _err(exc, 409)
        except NfeValidationError as exc:
            import json

            try:
                field_errors = json.loads(str(exc))
            except json.JSONDecodeError:
                field_errors = [{"message": str(exc)}]
            return Response(
                {
                    "detail": "validação falhou",
                    "code": exc.code,
                    "field_errors": field_errors,
                },
                status=422,
            )
        except NfeDisabledError as exc:
            return _err(exc, 403)
        except NfeInvalidTransitionError as exc:
            return _err(exc, 400)
        return Response(NfeInvoiceSerializer(inv).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        ser = NfeCancelSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            cancel_invoice(
                inv,
                justificativa=ser.validated_data["justificativa"],
                actor=getattr(request.user, "email", "api") or "api",
            )
            inv.refresh_from_db()
        except NfeDisabledError as exc:
            return _err(exc, 403)
        except (NfeInvalidTransitionError, NfeValidationError) as exc:
            return _err(exc, 400)
        return Response(NfeInvoiceSerializer(inv).data)

    @action(detail=True, methods=["post"], url_path="discard")
    def discard(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        try:
            discard_draft(inv, actor=getattr(request.user, "email", "api") or "api")
        except NfeDisabledError as exc:
            return _err(exc, 403)
        except NfeInvalidTransitionError as exc:
            return _err(exc, 400)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        ser = NfeCloneSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            clone = clone_invoice(
                inv,
                idempotency_key=ser.validated_data["idempotency_key"],
                actor=getattr(request.user, "email", "api") or "api",
            )
        except NfeDisabledError as exc:
            return _err(exc, 403)
        except NfeInvalidTransitionError as exc:
            return _err(exc, 400)
        except NfeGateError as exc:
            return _err(exc, 400)
        return Response(NfeInvoiceSerializer(clone).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="artifacts/xml")
    def artifacts_xml(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        if inv.status not in {
            NfeInvoice.Status.AUTHORIZED,
            NfeInvoice.Status.CANCELLED,
        }:
            return Response(
                {"detail": "XML disponível só para autorizada/cancelada", "code": "nfe_artifact"},
                status=404,
            )
        art = get_artifact(inv, NfeArtifact.Kind.XML_AUTHORIZED)
        if art is None:
            return Response(
                {"detail": "XML ainda não disponível", "code": "nfe_artifact_missing"},
                status=404,
            )
        data = read_artifact_bytes(art)
        filename = f"nfe-{inv.access_key or inv.id}.xml"
        resp = HttpResponse(data, content_type="application/xml; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["X-Checksum-SHA256"] = art.checksum_sha256
        return resp

    @action(detail=True, methods=["get"], url_path="artifacts/pdf")
    def artifacts_pdf(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        if inv.status not in {
            NfeInvoice.Status.AUTHORIZED,
            NfeInvoice.Status.CANCELLED,
        }:
            return Response(
                {"detail": "DANFE disponível só para autorizada/cancelada", "code": "nfe_artifact"},
                status=404,
            )
        if not has_danfe_pdf(inv):
            return Response(
                {
                    "detail": "DANFE ainda não disponível (I2)",
                    "code": "nfe_danfe_missing",
                    "pdf_pending": True,
                },
                status=404,
            )
        art = get_artifact(inv, NfeArtifact.Kind.DANFE_PDF)
        data = read_artifact_bytes(art)
        filename = f"danfe-{inv.access_key or inv.id}.pdf"
        resp = HttpResponse(data, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["X-Checksum-SHA256"] = art.checksum_sha256
        return resp
