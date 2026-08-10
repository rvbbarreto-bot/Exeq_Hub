from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.food.exceptions import (
    FoodError,
    FoodInvalidOrderError,
    FoodInvalidTransitionError,
    FoodOrderNotFoundError,
    FoodPaymentError,
)
from apps.food.models import (
    FoodBom,
    FoodCapacitySlot,
    FoodCoupon,
    FoodCustomer,
    FoodDeliveryRoute,
    FoodDeliveryStop,
    FoodMarketplaceConnection,
    FoodOrder,
    FoodProduct,
    FoodProductionOrder,
    FoodPurchase,
    FoodRetentionRule,
    FoodSupplier,
)
from apps.food.operations import (
    assign_order_to_route,
    receive_purchase,
    sync_all_marketplace_connections,
    sync_marketplace_connection,
    transition_order_status,
    update_delivery_stop_status,
)
from apps.food.production import (
    complete_production,
    start_production,
)
from apps.food.retention import food_dashboard_metrics, process_retention_tick
from apps.food.serializers import (
    FoodBomCreateSerializer,
    FoodBomSerializer,
    FoodCapacitySlotSerializer,
    FoodCouponCreateSerializer,
    FoodCouponSerializer,
    FoodCustomerSerializer,
    FoodDeliveryRouteSerializer,
    FoodDeliveryStopSerializer,
    FoodMarketplaceConnectionSerializer,
    FoodOrderCreateSerializer,
    FoodOrderSerializer,
    FoodProductSerializer,
    FoodProductionOrderCreateSerializer,
    FoodProductionOrderSerializer,
    FoodPurchaseCreateSerializer,
    FoodPurchaseSerializer,
    FoodRetentionRuleCreateSerializer,
    FoodRetentionRuleSerializer,
    FoodSupplierSerializer,
    MarketplaceImportSerializer,
)
from apps.food.services import create_pix_intent_for_order
from shared.pagination import HubPageNumberPagination


class TenantQuerysetMixin:
    def get_queryset(self):
        return self.queryset.filter(tenant=self.request.tenant)


class FoodCustomerViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = FoodCustomer.objects.all().order_by("name")
    serializer_class = FoodCustomerSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = HubPageNumberPagination


class FoodProductViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = FoodProduct.objects.all().order_by("sku")
    serializer_class = FoodProductSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = HubPageNumberPagination


class FoodCouponViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodCoupon.objects.all().order_by("-created_at")
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(FoodCouponSerializer(page, many=True).data)

    def create(self, request, *args, **kwargs):
        ser = FoodCouponCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        coupon = ser.save()
        return Response(FoodCouponSerializer(coupon).data, status=status.HTTP_201_CREATED)


class FoodRetentionRuleViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodRetentionRule.objects.all().order_by("name")
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(
            FoodRetentionRuleSerializer(page, many=True).data
        )

    def create(self, request, *args, **kwargs):
        ser = FoodRetentionRuleCreateSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        rule = ser.save()
        return Response(
            FoodRetentionRuleSerializer(rule).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["post"], url_path="tick")
    def tick(self, request):
        return Response(process_retention_tick(tenant=request.tenant))


class FoodDashboardView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        return Response(food_dashboard_metrics(tenant=request.tenant))


class FoodSupplierViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = FoodSupplier.objects.all().order_by("name")
    serializer_class = FoodSupplierSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = HubPageNumberPagination


class FoodPurchaseViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodPurchase.objects.all().select_related("supplier").prefetch_related(
        "lines"
    )
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return super().get_queryset().order_by("-created_at")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(
            FoodPurchaseSerializer(page, many=True).data
        )

    def retrieve(self, request, *args, **kwargs):
        return Response(FoodPurchaseSerializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        ser = FoodPurchaseCreateSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        purchase = ser.save()
        purchase = (
            FoodPurchase.objects.select_related("supplier")
            .prefetch_related("lines")
            .get(pk=purchase.pk)
        )
        return Response(
            FoodPurchaseSerializer(purchase).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        try:
            purchase = receive_purchase(tenant=request.tenant, purchase_id=pk)
        except FoodInvalidTransitionError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        except FoodError as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "food_error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        purchase = (
            FoodPurchase.objects.select_related("supplier")
            .prefetch_related("lines")
            .get(pk=purchase.pk)
        )
        return Response(FoodPurchaseSerializer(purchase).data)


class FoodDeliveryRouteViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodDeliveryRoute.objects.all().order_by("-service_date", "-created_at")
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(
            FoodDeliveryRouteSerializer(page, many=True).data
        )

    def create(self, request, *args, **kwargs):
        ser = FoodDeliveryRouteSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        route = ser.save()
        return Response(
            FoodDeliveryRouteSerializer(route).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        order_id = request.data.get("order_id")
        sequence = request.data.get("sequence")
        try:
            stop = assign_order_to_route(
                tenant=request.tenant,
                route_id=pk,
                order_id=order_id,
                sequence=int(sequence) if sequence is not None else None,
            )
        except FoodOrderNotFoundError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_404_NOT_FOUND,
            )
        except FoodInvalidTransitionError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        except FoodError as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "food_error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(
            FoodDeliveryStopSerializer(stop).data, status=status.HTTP_201_CREATED
        )


class FoodDeliveryStopViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodDeliveryStop.objects.all().select_related("order", "route")
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset().order_by("route_id", "sequence")
        route_id = (request.query_params.get("route_id") or "").strip()
        if route_id:
            qs = qs.filter(route_id=route_id)
        return Response(FoodDeliveryStopSerializer(qs[:200], many=True).data)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        to_status = (request.data.get("status") or "").strip()
        try:
            stop = update_delivery_stop_status(
                tenant=request.tenant, stop_id=pk, to_status=to_status
            )
        except FoodInvalidTransitionError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        except FoodError as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "food_error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(FoodDeliveryStopSerializer(stop).data)


class FoodMarketplaceConnectionViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodMarketplaceConnection.objects.all().order_by("provider")
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        return Response(
            FoodMarketplaceConnectionSerializer(self.get_queryset(), many=True).data
        )

    def create(self, request, *args, **kwargs):
        ser = FoodMarketplaceConnectionSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        conn = ser.save()
        return Response(
            FoodMarketplaceConnectionSerializer(conn).data,
            status=status.HTTP_201_CREATED,
        )


class FoodMarketplaceImportView(APIView):
    permission_classes = [IsTenantWriter]

    def post(self, request):
        ser = MarketplaceImportSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        order = ser.save()
        order = (
            FoodOrder.objects.select_related(
                "customer", "charge", "coupon", "marketplace_connection"
            )
            .prefetch_related("lines")
            .get(pk=order.pk)
        )
        return Response(FoodOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class FoodMarketplaceSyncView(APIView):
    """
    POST body opcional: { "connection_id": "<uuid>" }.
    Sem id: sincroniza todas as conexões ativas do tenant.
    """

    permission_classes = [IsTenantWriter]

    def post(self, request):
        cid = request.data.get("connection_id") if hasattr(request, "data") else None
        try:
            if cid:
                result = sync_marketplace_connection(
                    tenant=request.tenant, connection_id=cid
                )
                return Response(result)
            return Response(
                {"results": sync_all_marketplace_connections(tenant=request.tenant)}
            )
        except FoodError as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "food_error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )


class FoodOrderViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = (
        FoodOrder.objects.all()
        .select_related("customer", "charge", "coupon", "marketplace_connection")
        .prefetch_related("lines")
    )
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().order_by("-created_at")
        status_filter = (self.request.query_params.get("status") or "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        payment = (self.request.query_params.get("payment_status") or "").strip()
        if payment:
            qs = qs.filter(payment_status=payment)
        channel = (self.request.query_params.get("channel") or "").strip()
        if channel:
            qs = qs.filter(channel=channel)
        return qs

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(FoodOrderSerializer(page, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return Response(FoodOrderSerializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        ser = FoodOrderCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        order = ser.save()
        order = (
            FoodOrder.objects.select_related(
                "customer", "charge", "coupon", "marketplace_connection"
            )
            .prefetch_related("lines")
            .get(pk=order.pk)
        )
        return Response(FoodOrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="pix")
    def pix(self, request, pk=None):
        try:
            order = create_pix_intent_for_order(tenant=request.tenant, order_id=pk)
        except FoodOrderNotFoundError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_404_NOT_FOUND,
            )
        except FoodInvalidTransitionError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        except (FoodInvalidOrderError, FoodPaymentError, FoodError) as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "food_error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        order = (
            FoodOrder.objects.select_related(
                "customer", "charge", "coupon", "marketplace_connection"
            )
            .prefetch_related("lines")
            .get(pk=order.pk)
        )
        return Response(FoodOrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        to_status = (request.data.get("status") or "").strip()
        try:
            order = transition_order_status(
                tenant=request.tenant, order_id=pk, to_status=to_status
            )
        except FoodOrderNotFoundError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_404_NOT_FOUND,
            )
        except FoodInvalidTransitionError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(FoodOrderSerializer(order).data)


class FoodBomViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodBom.objects.all().prefetch_related("components").order_by("-created_at")
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(FoodBomSerializer(page, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return Response(FoodBomSerializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        ser = FoodBomCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        bom = ser.save()
        bom = FoodBom.objects.prefetch_related("components").get(pk=bom.pk)
        return Response(FoodBomSerializer(bom).data, status=status.HTTP_201_CREATED)


class FoodCapacitySlotViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodCapacitySlot.objects.all().order_by("service_date", "starts_at")
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(
            FoodCapacitySlotSerializer(page, many=True).data
        )

    def create(self, request, *args, **kwargs):
        ser = FoodCapacitySlotSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        slot = ser.save()
        return Response(
            FoodCapacitySlotSerializer(slot).data, status=status.HTTP_201_CREATED
        )


class FoodProductionOrderViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = FoodProductionOrder.objects.all().select_related(
        "product", "bom", "capacity_slot"
    )
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return super().get_queryset().order_by("-created_at")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(
            FoodProductionOrderSerializer(page, many=True).data
        )

    def retrieve(self, request, *args, **kwargs):
        return Response(FoodProductionOrderSerializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        ser = FoodProductionOrderCreateSerializer(
            data=request.data, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        op = ser.save()
        return Response(
            FoodProductionOrderSerializer(op).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        try:
            op = start_production(tenant=request.tenant, production_order_id=pk)
        except FoodInvalidTransitionError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        except FoodError as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "food_error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(FoodProductionOrderSerializer(op).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        qty = request.data.get("quantity_produced")
        try:
            op = complete_production(
                tenant=request.tenant,
                production_order_id=pk,
                quantity_produced=qty,
            )
        except FoodInvalidTransitionError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        except FoodError as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "food_error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(FoodProductionOrderSerializer(op).data)


class FoodMrpView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        from apps.food.production import mrp_suggestions

        return Response({"suggestions": mrp_suggestions(tenant=request.tenant)})


class FoodIntelligenceView(APIView):
    """Fase 4 — relatório consolidado ou seções via ?section=demand|customers|pricing|suggestions."""

    permission_classes = [IsTenantWriter]

    def get(self, request):
        from apps.food.intelligence import (
            customer_intelligence,
            demand_forecast,
            dynamic_pricing_suggestions,
            intelligence_report,
            production_and_purchase_suggestions,
        )

        lookback = int(request.query_params.get("lookback_days") or 28)
        horizon = int(request.query_params.get("horizon_days") or 7)
        section = (request.query_params.get("section") or "full").strip().lower()
        tenant = request.tenant

        if section == "demand":
            return Response(
                {
                    "demand_forecast": demand_forecast(
                        tenant=tenant,
                        lookback_days=lookback,
                        horizon_days=horizon,
                    )
                }
            )
        if section == "customers":
            return Response(
                {"customer_intelligence": customer_intelligence(tenant=tenant)}
            )
        if section == "pricing":
            return Response(
                {
                    "pricing_suggestions": dynamic_pricing_suggestions(
                        tenant=tenant, lookback_days=lookback
                    )
                }
            )
        if section == "suggestions":
            return Response(
                production_and_purchase_suggestions(
                    tenant=tenant, lookback_days=lookback, horizon_days=horizon
                )
            )
        return Response(
            intelligence_report(
                tenant=tenant, lookback_days=lookback, horizon_days=horizon
            )
        )
