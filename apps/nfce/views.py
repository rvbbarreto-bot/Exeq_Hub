from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.fiscal.document_policy import DocumentModel
from apps.master_data.models import Provider
from apps.nfce.exceptions import (
    NfceDisabledError,
    NfceGateError,
    NfceInvalidTransitionError,
    NfcePolicyError,
    NfceValidationError,
    NfceVersionConflictError,
)
from apps.nfce.gate import build_config_payload, build_gate_payload
from apps.nfce.models import NfceInvoice, NfceInvoiceEvent
from apps.nfce.serializers import (
    NfceCancelSerializer,
    NfceCheckoutSerializer,
    NfceDraftCreateSerializer,
    NfceEmitSerializer,
    NfceInvoiceSerializer,
    NfceItemsReplaceSerializer,
    NfcePolicyPreviewSerializer,
)
from apps.nfce.services import (
    cancel_nfce,
    checkout_and_emit_nfce,
    create_draft,
    emit_nfce,
    nfce_feature_enabled,
    replace_items,
    resolve_checkout_route,
    validate_invoice,
)
from apps.nfce.xml_export import resolve_authorized_xml_bytes
from shared.pagination import HubPageNumberPagination
from shared.validators import validate_cpf


def _err(exc, http=400):
    return Response({"detail": str(exc), "code": getattr(exc, "code", "nfce_error")}, status=http)


class NfceWriteThrottle(UserRateThrottle):
    scope = "nfe_write"


class NfceGateView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        provider_id = (request.query_params.get("provider_id") or "").strip() or None
        series = request.query_params.get("series")
        tp_amb = (request.query_params.get("tp_amb") or "").strip() or None
        try:
            ser = int(series) if series not in (None, "") else None
        except (TypeError, ValueError):
            return Response({"detail": "series inválida", "code": "nfce_gate"}, status=400)
        return Response(
            build_gate_payload(
                tenant=request.tenant,
                provider_id=provider_id,
                series=ser,
                tp_amb=tp_amb,
            )
        )


class NfceConfigView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        provider_id = (request.query_params.get("provider_id") or "").strip() or None
        return Response(build_config_payload(tenant=request.tenant, provider_id=provider_id))


class NfcePolicyPreviewView(APIView):
    """POST /nfce/policy/preview — roteamento CPF/CNPJ antes do checkout."""

    permission_classes = [IsTenantWriter]

    def post(self, request):
        ser = NfcePolicyPreviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        provider = get_object_or_404(Provider, pk=data["provider_id"], tenant=request.tenant)
        try:
            route = resolve_checkout_route(
                provider=provider,
                total_cents=data["total_cents"],
                cpf=data.get("cpf") or None,
                cnpj=data.get("cnpj") or None,
                delivery=data.get("delivery") or False,
                installment=data.get("installment") or False,
            )
        except NfcePolicyError as exc:
            import json

            try:
                errors = json.loads(str(exc))
            except json.JSONDecodeError:
                errors = [{"message": str(exc)}]
            return Response(
                {"ok": False, "model": DocumentModel.BLOCKED.value, "errors": errors},
                status=422,
            )
        return Response(
            {
                "ok": True,
                "model": route.model.value,
                "omit_dest": route.omit_dest,
                "reasons": list(route.reasons),
                "redirect_nfe": route.model == DocumentModel.NFE,
            }
        )


class NfceCheckoutView(APIView):
    """POST /nfce/checkout — PDV one-shot (policy + emit)."""

    permission_classes = [IsTenantWriter]
    throttle_classes = [NfceWriteThrottle]

    def post(self, request):
        ser = NfceCheckoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        provider = get_object_or_404(Provider, pk=data["provider_id"], tenant=request.tenant)
        try:
            result = checkout_and_emit_nfce(
                tenant=request.tenant,
                provider=provider,
                items=data["items"],
                idempotency_key=data["idempotency_key"],
                cpf=data.get("cpf") or None,
                cnpj=data.get("cnpj") or None,
                delivery=data.get("delivery") or False,
                payment_method=(data.get("payment_method") or "").strip() or None,
                actor=getattr(request.user, "email", "api") or "api",
            )
        except (NfceDisabledError, NfceGateError) as exc:
            return _err(exc, 403)
        except NfcePolicyError as exc:
            return _err(exc, 422)
        except NfceValidationError as exc:
            import json

            try:
                field_errors = json.loads(str(exc))
            except json.JSONDecodeError:
                field_errors = [{"message": str(exc)}]
            return Response(
                {"detail": "validação falhou", "code": exc.code, "field_errors": field_errors},
                status=422,
            )

        if isinstance(result, dict) and result.get("route") == "nfe":
            return Response(result, status=409)

        return Response(NfceInvoiceSerializer(result).data, status=status.HTTP_202_ACCEPTED)


class NfceInvoiceViewSet(viewsets.ViewSet):
    permission_classes = [IsTenantWriter]

    def get_throttles(self):
        if self.action in {"create", "emit", "checkout"}:
            return [NfceWriteThrottle()]
        return []

    def list(self, request):
        qs = (
            NfceInvoice.objects.filter(tenant=request.tenant)
            .select_related("provider")
            .order_by("-created_at")
        )
        status_q = (request.query_params.get("status") or "").strip()
        if status_q:
            qs = qs.filter(status=status_q)
        page = HubPageNumberPagination()
        result = page.paginate_queryset(qs, request)
        ser = NfceInvoiceSerializer(result, many=True)
        return page.get_paginated_response(ser.data)

    def retrieve(self, request, pk=None):
        inv = get_object_or_404(NfceInvoice, pk=pk, tenant=request.tenant)
        return Response(NfceInvoiceSerializer(inv).data)

    def create(self, request):
        ser = NfceDraftCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        provider = get_object_or_404(Provider, pk=data["provider_id"], tenant=request.tenant)
        ident: dict = {}
        omit_dest = data.get("omit_dest")
        cpf_raw = (data.get("cpf") or "").strip()
        if cpf_raw:
            ident = {
                "document": validate_cpf(cpf_raw),
                "document_type": "cpf",
                "name": "CONSUMIDOR",
            }
            omit_dest = False
        if omit_dest is None:
            omit_dest = not bool(ident)
        try:
            inv = create_draft(
                tenant=request.tenant,
                provider=provider,
                idempotency_key=data["idempotency_key"],
                nature_operation=data.get("nature_operation") or "VENDA",
                series=data.get("series") or 1,
                tp_amb=data.get("tp_amb"),
                issue_date=data.get("issue_date"),
                identification_snapshot=ident,
                omit_dest=bool(omit_dest),
                actor=getattr(request.user, "email", "api") or "api",
            )
        except (NfceDisabledError, NfceGateError) as exc:
            return _err(exc, 403)
        return Response(NfceInvoiceSerializer(inv).data, status=status.HTTP_201_CREATED)

    def items(self, request, pk=None):
        inv = get_object_or_404(NfceInvoice, pk=pk, tenant=request.tenant)
        ser = NfceItemsReplaceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            replace_items(
                inv,
                items=ser.validated_data["items"],
                expected_version=ser.validated_data.get("version"),
            )
            inv.refresh_from_db()
        except NfceVersionConflictError as exc:
            return _err(exc, 409)
        except (NfceDisabledError, NfceInvalidTransitionError) as exc:
            return _err(exc, 403 if isinstance(exc, NfceDisabledError) else 400)
        return Response(NfceInvoiceSerializer(inv).data)

    def validate(self, request, pk=None):
        inv = get_object_or_404(NfceInvoice, pk=pk, tenant=request.tenant)
        try:
            result = validate_invoice(inv)
            inv.refresh_from_db()
        except (NfceDisabledError, NfceInvalidTransitionError) as exc:
            return _err(exc, 403 if isinstance(exc, NfceDisabledError) else 400)
        return Response({"validation": result, "invoice": NfceInvoiceSerializer(inv).data})

    def emit(self, request, pk=None):
        inv = get_object_or_404(NfceInvoice, pk=pk, tenant=request.tenant)
        ser = NfceEmitSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        try:
            emit_nfce(
                inv,
                expected_version=ser.validated_data.get("version"),
                actor=getattr(request.user, "email", "api") or "api",
            )
            inv.refresh_from_db()
        except NfceVersionConflictError as exc:
            return _err(exc, 409)
        except NfceValidationError as exc:
            import json

            try:
                field_errors = json.loads(str(exc))
            except json.JSONDecodeError:
                field_errors = [{"message": str(exc)}]
            return Response(
                {"detail": "validação falhou", "code": exc.code, "field_errors": field_errors},
                status=422,
            )
        except (NfceDisabledError, NfceInvalidTransitionError) as exc:
            return _err(exc, 403 if isinstance(exc, NfceDisabledError) else 400)
        return Response(NfceInvoiceSerializer(inv).data, status=status.HTTP_202_ACCEPTED)

    def cancel(self, request, pk=None):
        inv = get_object_or_404(NfceInvoice, pk=pk, tenant=request.tenant)
        ser = NfceCancelSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        try:
            cancel_nfce(
                inv,
                justificativa=ser.validated_data["justificativa"],
                actor=getattr(request.user, "email", "api") or "api",
            )
            inv.refresh_from_db()
        except NfceValidationError as exc:
            return _err(exc, 422)
        except (NfceDisabledError, NfceInvalidTransitionError) as exc:
            return _err(exc, 403 if isinstance(exc, NfceDisabledError) else 400)
        return Response(NfceInvoiceSerializer(inv).data)

    def events(self, request, pk=None):
        inv = get_object_or_404(NfceInvoice, pk=pk, tenant=request.tenant)
        rows = NfceInvoiceEvent.objects.filter(tenant=request.tenant, invoice=inv).order_by(
            "occurred_at"
        )
        data = [
            {
                "id": str(ev.id),
                "from_status": ev.from_status,
                "to_status": ev.to_status,
                "actor": ev.actor,
                "metadata": ev.metadata,
                "occurred_at": ev.occurred_at.isoformat(),
            }
            for ev in rows
        ]
        return Response({"invoice_id": str(inv.id), "events": data})

    def artifacts_xml(self, request, pk=None):
        inv = get_object_or_404(NfceInvoice, pk=pk, tenant=request.tenant)
        from apps.nfce.artifacts import get_artifact, read_artifact_bytes
        from apps.nfce.models import NfceArtifact

        art = get_artifact(inv, NfceArtifact.Kind.XML_AUTHORIZED)
        if art is not None:
            return HttpResponse(read_artifact_bytes(art), content_type="application/xml")
        xml = resolve_authorized_xml_bytes(inv)
        if not xml:
            return Response(
                {"detail": "XML indisponível", "code": "nfce_artifact"},
                status=404,
            )
        return HttpResponse(xml, content_type="application/xml")

    def artifacts_pdf(self, request, pk=None):
        inv = get_object_or_404(NfceInvoice, pk=pk, tenant=request.tenant)
        xml = resolve_authorized_xml_bytes(inv)
        if not xml:
            return Response(
                {"detail": "PDF indisponível", "code": "nfce_artifact"},
                status=404,
            )
        from integrations.sefaz_nfe.danfe_nfce import render_danfce_for_invoice

        cancelled = inv.status == NfceInvoice.Status.CANCELLED
        return HttpResponse(
            render_danfce_for_invoice(inv, xml, cancelled=cancelled),
            content_type="application/pdf",
        )
