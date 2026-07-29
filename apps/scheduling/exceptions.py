from shared.exceptions import DomainError


class SchedulingError(DomainError):
    code = "scheduling_error"


class ServiceNotBookableError(SchedulingError):
    code = "service_not_bookable"


class AppointmentInPastError(SchedulingError):
    code = "appointment_in_past"


class SlotUnavailableError(SchedulingError):
    code = "slot_unavailable"


class ScheduleDurationMismatchError(SchedulingError):
    code = "schedule_duration_mismatch"


class ServicePriceMismatchError(SchedulingError):
    code = "service_price_mismatch"


class CustomerRestrictedError(SchedulingError):
    code = "customer_restricted"


class AppointmentNotFoundError(SchedulingError):
    code = "appointment_not_found"


class InvalidAppointmentTransitionError(SchedulingError):
    code = "invalid_appointment_transition"


class DuplicateIdempotencyKeyError(SchedulingError):
    code = "duplicate_idempotency_key"


class ProfessionalNotFoundError(SchedulingError):
    code = "professional_not_found"


class CustomerNotFoundError(SchedulingError):
    code = "customer_not_found"
