import hashlib
import hmac
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import Tenant
from apps.billing.exceptions import (
    ChargeNotFoundError,
    GatewayRegistrationError,
    IncompatiblePaymentError,
    InvalidWebhookSignatureError,
)
from apps.billing.models import Charge, PaymentEvent, WebhookInbox
from apps.ops.services import enqueue_outbox
from integrations.payments.errors import PaymentGatewayError
from integrations.payments.factory import get_payment_gateway
from integrations.payments.normalize import normalize_gateway_payload
from integrations.payments.router import resolve_payment_provider_kind


def verify_gateway_signature(*, body: bytes, signature: str) -> bool:
    secret = (settings.WEBHOOK_GATEWAY_SECRET or "").encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@transaction.atomic
def create_charge(
    *,
    tenant,
    idempotency_key: str,
    customer,
    amount_cents: int,
    due_date,
    description: str = "",
    nf_issue=None,
) -> Charge:
    existing = Charge.objects.filter(
        tenant=tenant,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing

    charge = Charge.objects.create(
        tenant=tenant,
        idempotency_key=idempotency_key,
        customer=customer,
        amount_cents=amount_cents,
        due_date=due_date,
        description=description,
        nf_issue=nf_issue,
        status=Charge.Status.PENDING,
    )

    gateway = get_payment_gateway(tenant=tenant)
    try:
        result = gateway.registrar_cobranca(
            amount_cents=amount_cents,
            due_date=due_date,
            description=description,
            customer_document=customer.document,
            customer_name=customer.name,
            external_reference=str(charge.id),
            idempotency_key=idempotency_key,
        )
    except PaymentGatewayError as exc:
        charge.status = Charge.Status.FAILED
        charge.save(update_fields=["status", "updated_at"])
        raise GatewayRegistrationError(str(exc)) from exc

    charge.gateway_ref = result.external_ref
    charge.status = Charge.Status.REGISTERED
    charge.save(update_fields=["gateway_ref", "status", "updated_at"])
    enqueue_outbox(
        tenant=tenant,
        event_type="charge.registered",
        aggregate_type="charge",
        aggregate_id=charge.id,
        payload={
            "charge_id": str(charge.id),
            "gateway_ref": charge.gateway_ref,
            "provider": gateway.kind,
        },
        correlation_id=charge.correlation_id,
    )
    return charge


@transaction.atomic
def cancel_charge(charge: Charge) -> Charge:
    if charge.status == Charge.Status.PAID:
        raise IncompatiblePaymentError("Cobrança paga não pode ser cancelada")
    if charge.status == Charge.Status.CANCELLED:
        return charge

    if charge.gateway_ref:
        gateway = get_payment_gateway(tenant=charge.tenant)
        try:
            gateway.cancelar(ref=charge.gateway_ref)
        except PaymentGatewayError as exc:
            raise GatewayRegistrationError(str(exc)) from exc

    charge.status = Charge.Status.CANCELLED
    charge.save(update_fields=["status", "updated_at"])
    enqueue_outbox(
        tenant=charge.tenant,
        event_type="charge.cancelled",
        aggregate_type="charge",
        aggregate_id=charge.id,
        payload={"charge_id": str(charge.id), "gateway_ref": charge.gateway_ref},
        correlation_id=charge.correlation_id,
    )
    return charge


@transaction.atomic
def ingest_gateway_webhook(
    *,
    raw_body: bytes,
    signature: str,
    payload: dict,
    provider: str | None = None,
) -> WebhookInbox:
    if not verify_gateway_signature(body=raw_body, signature=signature):
        raise InvalidWebhookSignatureError("Assinatura inválida")

    canonical = normalize_gateway_payload(payload)
    tenant = _resolve_tenant(canonical)
    provider_kind = resolve_payment_provider_kind(
        tenant=tenant,
        provider_kind=provider or canonical.get("provider"),
    )
    idempotency_key = canonical.get("idempotency_key")
    if not idempotency_key:
        raise ChargeNotFoundError("idempotency_key ausente")

    existing = WebhookInbox.objects.filter(
        tenant=tenant,
        provider=provider_kind,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        return existing

    inbox = WebhookInbox.objects.create(
        tenant=tenant,
        provider=provider_kind,
        idempotency_key=idempotency_key,
        status=WebhookInbox.Status.RECEIVED,
        signature=signature,
        signature_valid=True,
        raw_payload=canonical,
        payload_hash=WebhookInbox.hash_payload(canonical),
    )
    return process_webhook_inbox(inbox)


def _resolve_tenant(canonical: dict) -> Tenant:
    tenant_slug = (canonical.get("tenant_slug") or "").strip()
    if tenant_slug:
        try:
            return Tenant.objects.get(slug=tenant_slug, status=Tenant.Status.ACTIVE)
        except Tenant.DoesNotExist as exc:
            raise ChargeNotFoundError("Tenant inválido") from exc

    gateway_ref = canonical.get("gateway_ref") or ""
    external_reference = canonical.get("external_reference") or ""
    charge = None
    if gateway_ref:
        charge = Charge.objects.filter(gateway_ref=gateway_ref).select_related("tenant").first()
    if charge is None and external_reference:
        try:
            uuid.UUID(str(external_reference))
            charge = (
                Charge.objects.filter(id=external_reference)
                .select_related("tenant")
                .first()
            )
        except (ValueError, TypeError):
            charge = None
    if charge is None:
        raise ChargeNotFoundError("tenant_slug ausente e cobrança não encontrada")
    if charge.tenant.status != Tenant.Status.ACTIVE:
        raise ChargeNotFoundError("Tenant inválido")
    canonical["tenant_slug"] = charge.tenant.slug
    if not canonical.get("gateway_ref"):
        canonical["gateway_ref"] = charge.gateway_ref
    if not canonical.get("amount_cents"):
        canonical["amount_cents"] = charge.amount_cents
    return charge.tenant


@transaction.atomic
def process_webhook_inbox(inbox: WebhookInbox) -> WebhookInbox:
    if inbox.status == WebhookInbox.Status.PROCESSED:
        return inbox
    if not inbox.signature_valid:
        raise InvalidWebhookSignatureError("Inbox sem assinatura válida")

    inbox.status = WebhookInbox.Status.PROCESSING
    inbox.save(update_fields=["status", "updated_at"])

    payload = inbox.raw_payload
    gateway_ref = payload.get("gateway_ref")
    amount_cents = int(payload.get("amount_cents", 0))
    paid_at = parse_datetime(str(payload.get("paid_at") or "")) or timezone.now()

    try:
        charge = Charge.objects.select_for_update().get(
            tenant=inbox.tenant,
            gateway_ref=gateway_ref,
        )
    except Charge.DoesNotExist:
        ext = payload.get("external_reference")
        charge = None
        if ext:
            charge = (
                Charge.objects.select_for_update()
                .filter(tenant=inbox.tenant, id=ext)
                .first()
            )
        if charge is None:
            inbox.status = WebhookInbox.Status.FAILED
            inbox.error_message = "Cobrança não encontrada"
            inbox.save(update_fields=["status", "error_message", "updated_at"])
            return inbox

    if amount_cents != charge.amount_cents:
        inbox.status = WebhookInbox.Status.FAILED
        inbox.error_message = "Valor incompatível"
        inbox.save(update_fields=["status", "error_message", "updated_at"])
        return inbox

    if not PaymentEvent.objects.filter(webhook_inbox=inbox).exists():
        PaymentEvent.objects.create(
            tenant=inbox.tenant,
            charge=charge,
            webhook_inbox=inbox,
            amount_cents=amount_cents,
            paid_at=paid_at,
            gateway_ref=gateway_ref or charge.gateway_ref,
            metadata={"provider": inbox.provider},
        )

    if charge.status != Charge.Status.PAID:
        charge.status = Charge.Status.PAID
        charge.save(update_fields=["status", "updated_at"])
        enqueue_outbox(
            tenant=inbox.tenant,
            event_type="charge.paid",
            aggregate_type="charge",
            aggregate_id=charge.id,
            payload={"charge_id": str(charge.id)},
            correlation_id=charge.correlation_id,
        )

    inbox.status = WebhookInbox.Status.PROCESSED
    inbox.processed_at = timezone.now()
    inbox.error_message = ""
    inbox.save(update_fields=["status", "processed_at", "error_message", "updated_at"])
    return inbox


@transaction.atomic
def reprocess_webhook(inbox: WebhookInbox) -> WebhookInbox:
    if inbox.status not in {
        WebhookInbox.Status.FAILED,
        WebhookInbox.Status.RECEIVED,
        WebhookInbox.Status.PROCESSING,
    }:
        return inbox
    inbox.status = WebhookInbox.Status.RECEIVED
    inbox.error_message = ""
    inbox.save(update_fields=["status", "error_message", "updated_at"])
    return process_webhook_inbox(inbox)
