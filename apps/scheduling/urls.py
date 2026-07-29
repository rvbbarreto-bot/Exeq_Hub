from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.scheduling.views import (
    AppointmentViewSet,
    AvailabilityView,
    BusinessHoursViewSet,
    CalendarBlockViewSet,
    CommissionEntryViewSet,
    CommissionRuleViewSet,
    ProfessionalServiceViewSet,
    ProfessionalViewSet,
    ScheduleServiceViewSet,
)

router = DefaultRouter()
router.register(
    "scheduling/professionals", ProfessionalViewSet, basename="scheduling-professionals"
)
router.register(
    "scheduling/services", ScheduleServiceViewSet, basename="scheduling-services"
)
router.register(
    "scheduling/professional-services",
    ProfessionalServiceViewSet,
    basename="scheduling-professional-services",
)
router.register(
    "scheduling/business-hours",
    BusinessHoursViewSet,
    basename="scheduling-business-hours",
)
router.register(
    "scheduling/calendar-blocks",
    CalendarBlockViewSet,
    basename="scheduling-calendar-blocks",
)
router.register(
    "scheduling/appointments", AppointmentViewSet, basename="scheduling-appointments"
)
router.register(
    "scheduling/commission-rules",
    CommissionRuleViewSet,
    basename="scheduling-commission-rules",
)
router.register(
    "scheduling/commission-entries",
    CommissionEntryViewSet,
    basename="scheduling-commission-entries",
)

urlpatterns = [
    path(
        "scheduling/availability",
        AvailabilityView.as_view(),
        name="scheduling-availability",
    ),
    *router.urls,
]
