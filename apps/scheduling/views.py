from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantWriter
from apps.scheduling.exceptions import (
    AppointmentNotFoundError,
    InvalidAppointmentTransitionError,
    ProfessionalNotFoundError,
    SchedulingError,
    ServiceNotBookableError,
)
from apps.scheduling.models import (
    Appointment,
    AppointmentFinancial,
    BusinessHours,
    CalendarBlock,
    CommissionEntry,
    CommissionRule,
    Professional,
    ProfessionalService,
    Service,
)
from apps.scheduling.serializers import (
    AppointmentCreateSerializer,
    AppointmentFinancialSerializer,
    AppointmentSerializer,
    AvailabilityQuerySerializer,
    BusinessHoursSerializer,
    CalendarBlockSerializer,
    CommissionEntrySerializer,
    CommissionEntryStatusSerializer,
    CommissionRuleSerializer,
    DepositSerializer,
    ProfessionalSerializer,
    ProfessionalServiceSerializer,
    ScheduleServiceSerializer,
    SettleFinancialSerializer,
)
from apps.scheduling.services import (
    cancel_appointment,
    check_in_appointment,
    complete_appointment,
    confirm_appointment,
    list_availability_slots,
    mark_no_show,
    start_appointment,
)
from shared.pagination import HubPageNumberPagination


class TenantQuerysetMixin:
    def get_queryset(self):
        return self.queryset.filter(tenant=self.request.tenant)


class ProfessionalViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = Professional.objects.all().order_by("name")
    serializer_class = ProfessionalSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = HubPageNumberPagination


class ScheduleServiceViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = Service.objects.all().order_by("name")
    serializer_class = ScheduleServiceSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = HubPageNumberPagination


class ProfessionalServiceViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = ProfessionalService.objects.all().select_related(
        "professional", "service"
    )
    serializer_class = ProfessionalServiceSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "head", "options"]
    pagination_class = HubPageNumberPagination


class BusinessHoursViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = BusinessHours.objects.all().order_by("weekday", "starts_at")
    serializer_class = BusinessHoursSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = HubPageNumberPagination


class CalendarBlockViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = CalendarBlock.objects.all().order_by("-starts_at")
    serializer_class = CalendarBlockSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "head", "options"]
    pagination_class = HubPageNumberPagination


class AppointmentViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = Appointment.objects.all().select_related(
        "professional", "customer", "service"
    )
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().order_by("-starts_at")
        status_filter = (self.request.query_params.get("status") or "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        professional_id = (
            self.request.query_params.get("professional_id") or ""
        ).strip()
        if professional_id:
            qs = qs.filter(professional_id=professional_id)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return AppointmentCreateSerializer
        return AppointmentSerializer

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        ser = AppointmentSerializer(page, many=True)
        return self.get_paginated_response(ser.data)

    def retrieve(self, request, *args, **kwargs):
        return Response(AppointmentSerializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        serializer = AppointmentCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        appt = serializer.save()
        return Response(
            AppointmentSerializer(appt).data, status=status.HTTP_201_CREATED
        )

    def _transition_response(self, fn):
        try:
            appt = fn(tenant=self.request.tenant, appointment_id=self.kwargs["pk"])
        except AppointmentNotFoundError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_404_NOT_FOUND,
            )
        except InvalidAppointmentTransitionError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        except SchedulingError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(AppointmentSerializer(appt).data)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, pk=None):
        return self._transition_response(confirm_appointment)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        return self._transition_response(cancel_appointment)

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        return self._transition_response(check_in_appointment)

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        return self._transition_response(start_appointment)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        return self._transition_response(complete_appointment)

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        return self._transition_response(mark_no_show)

    @action(detail=True, methods=["get"], url_path="financial")
    def financial(self, request, pk=None):
        appt = self.get_object()
        fin = AppointmentFinancial.objects.filter(
            tenant=request.tenant, appointment=appt
        ).first()
        if fin is None:
            return Response(
                {"detail": "Financeiro ainda não gerado.", "code": "financial_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AppointmentFinancialSerializer(fin).data)

    @action(detail=True, methods=["post"], url_path="deposit")
    def deposit(self, request, pk=None):
        self.get_object()
        ser = DepositSerializer(
            data=request.data,
            context={"request": request, "appointment_id": self.kwargs["pk"]},
        )
        ser.is_valid(raise_exception=True)
        fin = ser.save()
        return Response(AppointmentFinancialSerializer(fin).data)

    @action(detail=True, methods=["post"], url_path="settle")
    def settle(self, request, pk=None):
        self.get_object()
        ser = SettleFinancialSerializer(
            data=request.data,
            context={"request": request, "appointment_id": self.kwargs["pk"]},
        )
        ser.is_valid(raise_exception=True)
        fin = ser.save()
        return Response(AppointmentFinancialSerializer(fin).data)


class CommissionRuleViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = CommissionRule.objects.all().order_by("-priority", "-created_at")
    serializer_class = CommissionRuleSerializer
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = HubPageNumberPagination


class CommissionEntryViewSet(TenantQuerysetMixin, viewsets.GenericViewSet):
    queryset = CommissionEntry.objects.all().select_related(
        "professional", "service", "appointment", "commission_rule"
    )
    permission_classes = [IsTenantWriter]
    pagination_class = HubPageNumberPagination
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset().order_by("-created_at")
        status_filter = (self.request.query_params.get("status") or "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        professional_id = (
            self.request.query_params.get("professional_id") or ""
        ).strip()
        if professional_id:
            qs = qs.filter(professional_id=professional_id)
        return qs

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        ser = CommissionEntrySerializer(page, many=True)
        return self.get_paginated_response(ser.data)

    def retrieve(self, request, *args, **kwargs):
        return Response(CommissionEntrySerializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        ser = CommissionEntryStatusSerializer(
            data=request.data,
            context={"request": request, "entry_id": self.kwargs["pk"]},
        )
        ser.is_valid(raise_exception=True)
        entry = ser.save()
        return Response(CommissionEntrySerializer(entry).data)


class AvailabilityView(APIView):
    permission_classes = [IsTenantWriter]

    def get(self, request):
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        try:
            slots = list_availability_slots(
                tenant=request.tenant,
                professional_id=data["professional_id"],
                service_id=data["service_id"],
                day=data["day"],
                slot_interval_minutes=data["slot_interval_minutes"],
            )
        except (ProfessionalNotFoundError, ServiceNotBookableError) as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "day": data["day"].isoformat(),
                "slots": [s.isoformat() for s in slots],
            }
        )
