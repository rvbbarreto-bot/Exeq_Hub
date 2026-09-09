"""API REST — fila fiscal iFood (Opção B)."""

from __future__ import annotations

from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantFoodWriter
from apps.food.exceptions import FoodInvalidOrderError, FoodOrderNotFoundError
from apps.food.fiscal.emit import emit_food_orders_batch
from apps.food.fiscal.ignore import ignore_food_order_fiscal
from apps.food.fiscal.mapping import (
    is_food_order_fiscally_ready,
    order_lines_mapping_summary,
)
from apps.food.fiscal.readiness import assess_food_order_fiscal_readiness
from apps.food.fiscal.observability import serialize_fiscal_event
from apps.food.models import FoodFiscalEvent, FoodOrder
from apps.food.tasks import emit_food_ifood_batch_task


def _serialize_food_order_fiscal(order: FoodOrder) -> dict:
    inv = order.nfce_invoice
    mapping = order_lines_mapping_summary(order)
    return {
        "id": str(order.id),
        "channel_ref": order.channel_ref,
        "customer_name": order.customer.name if order.customer_id else "",
        "logistic_status": order.status,
        "payment_status": order.payment_status,
        "total_cents": order.total_cents,
        "fiscal_status": order.fiscal_status or FoodOrder.FiscalStatus.PENDING,
        "fiscal_ready": is_food_order_fiscally_ready(order),
        "mapping": mapping,
        "fiscal_warnings": order.fiscal_warnings or [],
        "fiscal_rejection_code": order.fiscal_rejection_code,
        "fiscal_rejection_message": order.fiscal_rejection_message,
        "fiscal_ignored_at": (
            order.fiscal_ignored_at.isoformat() if order.fiscal_ignored_at else None
        ),
        "fiscal_ignored_reason": order.fiscal_ignored_reason,
        "nfce_invoice_id": str(order.nfce_invoice_id) if order.nfce_invoice_id else None,
        "nfce_access_key": inv.access_key if inv else "",
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


class FoodIfoodFiscalListView(APIView):
    """GET /api/v1/food/ifood/fiscal/ — pedidos iFood com status fiscal."""

    permission_classes = [IsTenantFoodWriter]

    def get(self, request):
        tenant = request.tenant
        qs = (
            FoodOrder.objects.filter(tenant=tenant, channel=FoodOrder.Channel.IFOOD)
            .select_related("customer", "nfce_invoice")
            .order_by("-created_at")
        )
        fiscal_status = (request.query_params.get("fiscal_status") or "").strip()
        if fiscal_status:
            qs = qs.filter(fiscal_status=fiscal_status)
        if request.query_params.get("failed_only") in {"1", "true", "yes"}:
            qs = qs.filter(
                fiscal_status__in=[
                    FoodOrder.FiscalStatus.REJECTED,
                    FoodOrder.FiscalStatus.FAILED,
                ]
            )
        pending_only = request.query_params.get("pending_only")
        if pending_only in {"1", "true", "yes"}:
            qs = qs.filter(
                Q(fiscal_status="")
                | Q(fiscal_status=FoodOrder.FiscalStatus.PENDING)
                | Q(fiscal_status=FoodOrder.FiscalStatus.REJECTED)
                | Q(fiscal_status=FoodOrder.FiscalStatus.FAILED)
            ).exclude(fiscal_status=FoodOrder.FiscalStatus.AUTHORIZED)

        if request.query_params.get("ignored_only") in {"1", "true", "yes"}:
            qs = qs.filter(fiscal_status=FoodOrder.FiscalStatus.IGNORED)

        limit = min(int(request.query_params.get("limit") or 50), 200)
        orders = list(qs[:limit])
        return Response(
            {
                "count": len(orders),
                "results": [_serialize_food_order_fiscal(o) for o in orders],
            }
        )


class FoodIfoodFiscalDetailView(APIView):
    """GET /api/v1/food/ifood/fiscal/<uuid>/ — detalhe + readiness."""

    permission_classes = [IsTenantFoodWriter]

    def get(self, request, order_id):
        order = (
            FoodOrder.objects.filter(
                tenant=request.tenant,
                pk=order_id,
                channel=FoodOrder.Channel.IFOOD,
            )
            .select_related("customer", "nfce_invoice")
            .first()
        )
        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        data = _serialize_food_order_fiscal(order)
        data["readiness"] = assess_food_order_fiscal_readiness(order)
        events = FoodFiscalEvent.objects.filter(tenant=request.tenant, order=order).order_by(
            "-occurred_at"
        )[:30]
        data["fiscal_events"] = [serialize_fiscal_event(ev) for ev in events]
        return Response(data)


class FoodIfoodEmitBatchView(APIView):
    """POST /api/v1/food/ifood/emit-batch/ — emissão supervisionada em lote."""

    permission_classes = [IsTenantFoodWriter]

    def post(self, request):
        raw_ids = request.data.get("order_ids") or []
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "order_ids (lista) é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        scoped = list(
            FoodOrder.objects.filter(
                tenant=request.tenant,
                pk__in=raw_ids,
                channel=FoodOrder.Channel.IFOOD,
            ).values_list("pk", flat=True)
        )
        if not scoped:
            return Response(
                {"detail": "Nenhum pedido iFood elegível neste tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order_ids = [str(x) for x in scoped]
        rejected = len(raw_ids) - len(scoped)
        async_mode = request.data.get("async", True)
        if async_mode in {False, "false", 0, "0"}:
            result = emit_food_orders_batch(
                tenant=request.tenant,
                order_ids=order_ids,
                actor=f"api:{getattr(request.user, 'email', 'api')}",
            )
            if rejected:
                result["rejected_cross_tenant"] = rejected
            return Response(result, status=status.HTTP_200_OK)

        task = emit_food_ifood_batch_task.delay(
            str(request.tenant.id),
            order_ids,
            actor=f"api:{getattr(request.user, 'email', 'api')}",
        )
        payload = {"task_id": task.id, "status": "queued", "order_ids": order_ids}
        if rejected:
            payload["rejected_cross_tenant"] = rejected
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class FoodIfoodFiscalIgnoreView(APIView):
    """POST /api/v1/food/ifood/fiscal/<uuid>/ignore/ — HP-06."""

    permission_classes = [IsTenantFoodWriter]

    def post(self, request, order_id):
        reason = (request.data.get("reason") or request.data.get("motivo") or "").strip()
        if not reason:
            return Response(
                {"detail": "reason (motivo) é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            order = ignore_food_order_fiscal(
                tenant=request.tenant,
                order_id=order_id,
                reason=reason,
                actor=f"api:{getattr(request.user, 'email', 'api')}",
            )
        except FoodOrderNotFoundError:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        except FoodInvalidOrderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_food_order_fiscal(order))
