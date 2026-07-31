"""Notificações WhatsApp do Agendador via Outbox (sem webhook de saída)."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from apps.ops.services import enqueue_outbox
from apps.scheduling.models import Appointment

EVENT_PENDING = "appointment.pending"
EVENT_CONFIRMED = "appointment.confirmed"
EVENT_CANCELLED = "appointment.cancelled"
EVENT_COMPLETED = "appointment.completed"


def _customer_phone(appointment: Appointment) -> str:
    customer = appointment.customer
    return str(getattr(customer, "whatsapp", "") or "").strip()


def _local_starts(appointment: Appointment) -> str:
    tz_name = (
        getattr(appointment.professional, "timezone", None) or "America/Sao_Paulo"
    )
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")
    local = appointment.starts_at.astimezone(tz)
    return local.strftime("%d/%m/%Y %H:%M")


def build_appointment_message(*, event_type: str, appointment: Appointment) -> str:
    when = _local_starts(appointment)
    pro = appointment.professional.name
    svc = appointment.service.name
    name = appointment.customer.name
    if event_type == EVENT_PENDING:
        return (
            f"Olá {name}, recebemos seu agendamento de {svc} com {pro} "
            f"em {when}. Aguardando confirmação."
        )
    if event_type == EVENT_CONFIRMED:
        return (
            f"Olá {name}, seu agendamento de {svc} com {pro} "
            f"em {when} está confirmado."
        )
    if event_type == EVENT_CANCELLED:
        return (
            f"Olá {name}, seu agendamento de {svc} com {pro} "
            f"em {when} foi cancelado."
        )
    if event_type == EVENT_COMPLETED:
        return (
            f"Olá {name}, obrigado! Seu atendimento de {svc} com {pro} "
            f"foi concluído."
        )
    return f"Atualização do agendamento de {svc} em {when}."


def enqueue_appointment_event(
    *, appointment: Appointment, event_type: str
) -> object | None:
    phone = _customer_phone(appointment)
    if not phone:
        return None
    body = build_appointment_message(event_type=event_type, appointment=appointment)
    return enqueue_outbox(
        tenant=appointment.tenant,
        event_type=event_type,
        aggregate_type="appointment",
        aggregate_id=appointment.id,
        payload={
            "phone_e164": phone,
            "message_body": body,
            "status": appointment.status,
            "starts_at": appointment.starts_at.isoformat(),
            "professional_name": appointment.professional.name,
            "service_name": appointment.service.name,
            "customer_name": appointment.customer.name,
        },
    )


def enqueue_for_created_appointment(appointment: Appointment) -> object | None:
    if appointment.status == Appointment.Status.PENDING:
        return enqueue_appointment_event(
            appointment=appointment, event_type=EVENT_PENDING
        )
    if appointment.status == Appointment.Status.CONFIRMED:
        return enqueue_appointment_event(
            appointment=appointment, event_type=EVENT_CONFIRMED
        )
    return None


def event_type_for_status(status: str) -> str | None:
    mapping = {
        Appointment.Status.PENDING: EVENT_PENDING,
        Appointment.Status.CONFIRMED: EVENT_CONFIRMED,
        Appointment.Status.CANCELLED: EVENT_CANCELLED,
        Appointment.Status.COMPLETED: EVENT_COMPLETED,
    }
    return mapping.get(status)
