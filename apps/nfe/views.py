from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
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
from apps.nfe.inutilization import inutilize_number_range
from apps.nfe.listing import filter_invoice_queryset, sanitize_event_metadata
from apps.nfe.metrics import compute_nfe_ops_metrics
from apps.nfe.models import NfeArtifact, NfeInvoice, NfeInvoiceEvent, NfeProduct
from apps.nfe.serializers import (
    NfeCancelSerializer,
    NfeCceSerializer,
    NfeCloneSerializer,
    NfeConfigSeriesSerializer,
    NfeDraftCreateSerializer,
    NfeEmitSerializer,
    NfeInutilizationSerializer,
    NfeInvoiceSerializer,
    NfeItemsReplaceSerializer,
    NfeProductSerializer,
    NfeResendEmailSerializer,
)
from apps.nfe.services import (
    cancel_invoice,
    clone_invoice,
    create_draft,
    discard_draft,
    emit_invoice,
    issue_carta_correcao,
    nfe_feature_enabled,
    replace_items,
    validate_invoice,
)
from shared.pagination import HubPageNumberPagination


def _err(exc, http=400):
    return Response({"detail": str(exc), "code": getattr(exc, "code", "nfe_error")}, status=http)


class NfeWriteThrottle(UserRateThrottle):
    """Limita create/emit/cancel/clone NF-e (paridade SEC-P1-02 NFS-e)."""

    scope = "nfe_write"


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


class NfeMetricsView(APIView):
    """GET /nfe/metrics/ — RF-91 KPIs operacionais (janela em dias)."""

    permission_classes = [IsTenantWriter]

    def get(self, request):
        raw = (request.query_params.get("days") or "30").strip()
        try:
            days = int(raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "days inválido", "code": "nfe_metrics"},
                status=400,
            )
        return Response(compute_nfe_ops_metrics(tenant=request.tenant, days=days))


class NfeConfigView(APIView):
    """GET/PUT /nfe/config/ — série, ambiente, próximo nº (T6). POST …/inutilize — U15."""

    permission_classes = [IsTenantWriter]
    throttle_classes = []

    def get_throttles(self):
        if self.request.method == "POST":
            return [NfeWriteThrottle()]
        return []

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


class NfeInutilizeView(APIView):
    """POST /nfe/config/inutilize — inutiliza faixa de nNF (U15)."""

    permission_classes = [IsTenantWriter]

    def get_throttles(self):
        return [NfeWriteThrottle()]

    def post(self, request):
        ser = NfeInutilizationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        provider = get_object_or_404(
            Provider, pk=data["provider_id"], tenant=request.tenant
        )
        try:
            row = inutilize_number_range(
                tenant=request.tenant,
                provider=provider,
                series=data.get("series") or 1,
                tp_amb=data.get("tp_amb"),
                n_ini=data["n_ini"],
                n_fin=data["n_fin"],
                x_just=data["x_just"],
                ano=data.get("ano") or None,
                actor=getattr(request.user, "email", "api") or "api",
            )
        except NfeDisabledError as exc:
            return _err(exc, 403)
        except NfeValidationError as exc:
            return _err(exc, 400)
        return Response(
            {
                "id": str(row.id),
                "status": row.status,
                "protocol": row.protocol,
                "series": row.series,
                "tp_amb": row.tp_amb,
                "ano": row.ano,
                "n_ini": row.n_ini,
                "n_fin": row.n_fin,
                "config": build_config_payload(
                    tenant=request.tenant, provider_id=str(provider.id)
                ),
            },
            status=status.HTTP_201_CREATED,
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

    def get_throttles(self):
        if self.action in {"create", "emit", "cancel", "clone", "cce", "resend_email"}:
            return [NfeWriteThrottle()]
        return []

    def list(self, request):
        qs = (
            NfeInvoice.objects.filter(tenant=request.tenant)
            .select_related("customer", "provider")
            .order_by("-created_at")
        )
        qs = filter_invoice_queryset(
            qs,
            status=request.query_params.get("status"),
            q=request.query_params.get("q"),
            date_from=request.query_params.get("date_from")
            or request.query_params.get("from"),
            date_to=request.query_params.get("date_to") or request.query_params.get("to"),
            days=request.query_params.get("days"),
            apply_default_period=request.query_params.get("all") not in {"1", "true", "yes"},
        )
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

    @action(detail=True, methods=["get"], url_path="events")
    def events(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        rows = list(
            NfeInvoiceEvent.objects.filter(tenant=request.tenant, invoice=inv).order_by(
                "occurred_at"
            )
        )
        data = []
        for ev in rows:
            data.append(
                {
                    "id": str(ev.id),
                    "from_status": ev.from_status,
                    "to_status": ev.to_status,
                    "actor": ev.actor,
                    "metadata": sanitize_event_metadata(ev.metadata),
                    "occurred_at": ev.occurred_at.isoformat()
                    if hasattr(ev.occurred_at, "isoformat")
                    else str(ev.occurred_at),
                }
            )
        return Response({"invoice_id": str(inv.id), "events": data})

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

    @action(detail=True, methods=["post"], url_path="cce")
    def cce(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        ser = NfeCceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            issue_carta_correcao(
                inv,
                x_correcao=ser.validated_data["x_correcao"],
                actor=getattr(request.user, "email", "api") or "api",
            )
            inv.refresh_from_db()
        except NfeDisabledError as exc:
            return _err(exc, 403)
        except (NfeInvalidTransitionError, NfeValidationError) as exc:
            return _err(exc, 400)
        return Response(NfeInvoiceSerializer(inv).data)

    @action(detail=True, methods=["post"], url_path="resend-email")
    def resend_email(self, request, pk=None):
        """RF-71 — reenvia XML+DANFE por e-mail (sem re-SEFAZ)."""
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        ser = NfeResendEmailSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        if inv.status != NfeInvoice.Status.AUTHORIZED:
            return _err(NfeInvalidTransitionError("resend-email só para autorizada"), 400)
        try:
            if not nfe_feature_enabled():
                raise NfeDisabledError("NF-e desabilitada")
            from apps.nfe.email_delivery import (
                NfeEmailDeliveryError,
                deliver_authorized_email,
            )

            ok = deliver_authorized_email(
                invoice=inv,
                to_email=ser.validated_data.get("email") or None,
                force=True,
            )
            if not ok:
                return Response(
                    {
                        "detail": "Sem destinatário de e-mail (cliente ou nfe_notify_email)",
                        "code": "nfe_email_missing",
                    },
                    status=400,
                )
            inv.refresh_from_db()
        except NfeDisabledError as exc:
            return _err(exc, 403)
        except NfeEmailDeliveryError as exc:
            return Response(
                {"detail": str(exc), "code": "nfe_email_failed"},
                status=502,
            )
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

    @action(detail=True, methods=["get"], url_path="artifacts/cce")
    def artifacts_cce(self, request, pk=None):
        inv = get_object_or_404(NfeInvoice, pk=pk, tenant=request.tenant)
        if inv.status not in {
            NfeInvoice.Status.AUTHORIZED,
            NfeInvoice.Status.CANCELLED,
        }:
            return Response(
                {"detail": "CCe disponível só para autorizada/cancelada", "code": "nfe_artifact"},
                status=404,
            )
        art = get_artifact(inv, NfeArtifact.Kind.XML_CCE)
        if art is None:
            return Response(
                {"detail": "XML CCe ainda não disponível", "code": "nfe_artifact_missing"},
                status=404,
            )
        data = read_artifact_bytes(art)
        filename = f"cce-{inv.access_key or inv.id}.xml"
        resp = HttpResponse(data, content_type="application/xml; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        resp["X-Checksum-SHA256"] = art.checksum_sha256
        return resp
