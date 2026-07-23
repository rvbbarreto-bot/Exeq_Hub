import hashlib
import hmac
import time
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import Tenant
from apps.billing.amount_rules import validate_charge_amount_cents
from apps.billing.exceptions import (
    ChargeNotFoundError,
    GatewayRegistrationError,
    IncompatiblePaymentError,
    InvalidChargeInputError,
    InvalidWebhookSignatureError,
)
from apps.billing.message_lines import split_message_lines
from apps.billing.models import Charge, PaymentEvent, WebhookInbox
from apps.billing.presets import (
    get_billing_preset,
    resolve_charge_options_from_preset,
)
from apps.billing.schedule import (
    build_due_dates,
    count_monthly_occurrences,
    seu_numero_for_installment,
    split_amount_cents,
)
from apps.ops.models import StoredFile
from apps.ops.services import enqueue_outbox
from integrations.payments.errors import PaymentGatewayError
from integrations.payments.factory import get_payment_gateway
from integrations.payments.inter_cancel import INTER_CANCEL_MOTIVOS
from integrations.payments.inter_status import map_inter_situacao
from integrations.payments.normalize import normalize_gateway_payload
from integrations.payments.router import resolve_payment_provider_kind
from shared.storage import get_storage
from uuid import uuid4

INSTALLMENT_MIN = 2
INSTALLMENT_MAX = 48
RECURRING_MAX = 60


def verify_gateway_signature(*, body: bytes, signature: str) -> bool:
    secret = (settings.WEBHOOK_GATEWAY_SECRET or "").encode()
    if not secret:
        return False
    # Aceita "hex" ou "sha256=<hex>" (proxies comuns).
    provided = (signature or "").strip()
    if provided.lower().startswith("sha256="):
        provided = provided.split("=", 1)[1].strip()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


def _normalize_seu_numero(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        raise InvalidChargeInputError("seu_numero (código de controle) é obrigatório")
    if len(text) > 15:
        raise InvalidChargeInputError("seu_numero deve ter no máximo 15 caracteres")
    return text


def _resolve_occurrence_plan(
    *,
    charge_kind: str,
    due_date,
    amount_cents: int,
    installment_count: int | None,
    recurrence_end_date,
) -> tuple[list[int], list]:
    if charge_kind == Charge.ChargeKind.SIMPLE:
        return [amount_cents], [due_date]

    if charge_kind == Charge.ChargeKind.INSTALLMENT:
        count = int(installment_count or 0)
        if count < INSTALLMENT_MIN or count > INSTALLMENT_MAX:
            raise InvalidChargeInputError(
                f"installment_count deve estar entre {INSTALLMENT_MIN} e {INSTALLMENT_MAX}"
            )
        return split_amount_cents(amount_cents, count), build_due_dates(
            first_due=due_date, count=count
        )

    if charge_kind == Charge.ChargeKind.RECURRING:
        if recurrence_end_date is None and not installment_count:
            raise InvalidChargeInputError(
                "recorrente exige recurrence_end_date ou installment_count"
            )
        if installment_count:
            count = int(installment_count)
        else:
            count = count_monthly_occurrences(
                first_due=due_date, end_date=recurrence_end_date
            )
        if count < 1 or count > RECURRING_MAX:
            raise InvalidChargeInputError(
                f"recorrência deve gerar entre 1 e {RECURRING_MAX} cobranças"
            )
        # Valor informado é o de cada ocorrência (como no IB Inter).
        return [amount_cents] * count, build_due_dates(first_due=due_date, count=count)

    raise InvalidChargeInputError(f"charge_kind inválido: {charge_kind}")


def _register_one(
    *,
    charge: Charge,
    gateway,
    idempotency_key: str,
    charge_options: dict,
) -> Charge:
    try:
        result = gateway.registrar_cobranca(
            amount_cents=charge.amount_cents,
            due_date=charge.due_date,
            description=charge.description,
            customer_document=charge.customer.document,
            customer_name=charge.customer.name,
            external_reference=charge.seu_numero or str(charge.id),
            idempotency_key=idempotency_key,
            customer_address=charge.customer.address or {},
            customer_email=getattr(charge.customer, "email", "") or "",
            charge_options=charge_options,
        )
    except PaymentGatewayError as exc:
        charge.status = Charge.Status.FAILED
        charge.save(update_fields=["status", "updated_at"])
        raise GatewayRegistrationError(str(exc)) from exc

    charge.gateway_ref = result.external_ref
    charge.status = Charge.Status.REGISTERED
    update_fields = ["gateway_ref", "status", "updated_at"]
    update_fields.extend(
        _apply_boleto_result(charge, result, include_status=False, include_payload=True)
    )
    charge.save(update_fields=list(dict.fromkeys(update_fields)))

    # Inter (e afins) costumam só devolver codigoSolicitacao no POST — enriquecer via GET.
    if not (charge.digitable_line or charge.pix_copy_paste):
        _enrich_boleto_artifacts(charge, gateway)

    try:
        ensure_charge_pdf(charge)
    except Exception:
        # Best-effort: PDF pode atrasar (EM_PROCESSAMENTO) sem falhar a emissão.
        pass

    enqueue_outbox(
        tenant=charge.tenant,
        event_type="charge.registered",
        aggregate_type="charge",
        aggregate_id=charge.id,
        payload={
            "charge_id": str(charge.id),
            "gateway_ref": charge.gateway_ref,
            "provider": gateway.kind,
            "charge_kind": charge.charge_kind,
        },
        correlation_id=charge.correlation_id,
    )
    charge.refresh_from_db()
    return charge


def _apply_boleto_result(
    charge: Charge,
    result,
    *,
    include_status: bool = True,
    include_payload: bool = True,
) -> list[str]:
    """Copia artefatos do ChargeRegisterResult para o model. Retorna campos alterados."""
    update_fields: list[str] = []
    if include_payload and result.raw is not None:
        charge.gateway_payload = result.raw
        update_fields.append("gateway_payload")
    if result.digitable_line:
        charge.digitable_line = result.digitable_line
        update_fields.append("digitable_line")
    if result.barcode:
        charge.barcode = result.barcode
        update_fields.append("barcode")
    if result.pix_copy_paste:
        charge.pix_copy_paste = result.pix_copy_paste
        update_fields.append("pix_copy_paste")
    if result.payment_url:
        charge.payment_url = result.payment_url
        update_fields.append("payment_url")
    if result.boleto_pdf_url:
        charge.boleto_pdf_url = result.boleto_pdf_url
        update_fields.append("boleto_pdf_url")

    extras = result.extras or {}
    seu = (extras.get("seu_numero") or "").strip()
    if seu and not charge.seu_numero:
        charge.seu_numero = seu[:15]
        update_fields.append("seu_numero")

    if include_status:
        new_status = result.status
        if new_status and new_status != charge.status:
            if charge.status == Charge.Status.PAID and new_status != Charge.Status.PAID:
                pass
            elif (
                charge.status == Charge.Status.CANCELLED
                and new_status != Charge.Status.CANCELLED
            ):
                pass
            else:
                charge.status = new_status
                update_fields.append("status")
    return update_fields


def _enrich_boleto_artifacts(charge: Charge, gateway, *, attempts: int = 3) -> Charge:
    """Best-effort GET detalhe após emissão (não falha o create se o GET atrasar)."""
    if not charge.gateway_ref:
        return charge
    for i in range(attempts):
        try:
            result = gateway.consultar_cobranca(ref=charge.gateway_ref)
        except PaymentGatewayError:
            if i >= attempts - 1:
                break
            time.sleep(0.35 * (i + 1))
            continue
        fields = _apply_boleto_result(
            charge, result, include_status=True, include_payload=True
        )
        if fields:
            charge.save(
                update_fields=list(dict.fromkeys([*fields, "updated_at"]))
            )
        if charge.digitable_line or charge.pix_copy_paste:
            return charge
        time.sleep(0.35 * (i + 1))
    return charge


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
    seu_numero: str | None = None,
    message_lines: list[str] | None = None,
    charge_kind: str = Charge.ChargeKind.SIMPLE,
    installment_count: int | None = None,
    recurrence_end_date=None,
) -> Charge | list[Charge]:
    existing = Charge.objects.filter(
        tenant=tenant,
        idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.gateway_ref:
            if existing.schedule_group_id:
                return list(
                    Charge.objects.filter(
                        tenant=tenant,
                        schedule_group_id=existing.schedule_group_id,
                    ).order_by("installment_number", "due_date")
                )
            return existing
        # Cadastro Admin/local sem emissão: completar no gateway
        if existing.status in {
            Charge.Status.PENDING,
            Charge.Status.FAILED,
        }:
            return emit_pending_charge(existing)
        return existing

    try:
        validate_charge_amount_cents(amount_cents)
    except ValueError as exc:
        raise InvalidChargeInputError(str(exc)) from exc

    from apps.billing.due_date_rules import validate_due_date

    try:
        validate_due_date(due_date)
    except ValueError as exc:
        raise InvalidChargeInputError(str(exc)) from exc

    kind = (charge_kind or Charge.ChargeKind.SIMPLE).strip().lower()
    if kind not in Charge.ChargeKind.values:
        raise InvalidChargeInputError(f"charge_kind inválido: {charge_kind}")

    control = _normalize_seu_numero(seu_numero) if seu_numero is not None else ""
    if not control:
        # Compat: emissão antiga sem código de controle explícito.
        control = str(uuid.uuid4()).replace("-", "")[:15]

    try:
        lines = split_message_lines(description, lines=message_lines)
    except ValueError as exc:
        raise InvalidChargeInputError(str(exc)) from exc

    amounts, dues = _resolve_occurrence_plan(
        charge_kind=kind,
        due_date=due_date,
        amount_cents=amount_cents,
        installment_count=installment_count,
        recurrence_end_date=recurrence_end_date,
    )
    total = len(amounts)
    group_id = uuid.uuid4() if total > 1 else None
    preset = get_billing_preset(tenant=tenant)
    option_snap = resolve_charge_options_from_preset(preset)
    multa = (
        Decimal(str(option_snap["multa_percent"]))
        if option_snap.get("multa_percent") is not None
        else None
    )
    mora = (
        Decimal(str(option_snap["mora_percent_am"]))
        if option_snap.get("mora_percent_am") is not None
        else None
    )

    gateway = get_payment_gateway(tenant=tenant)
    charges: list[Charge] = []
    for index, (part_amount, part_due) in enumerate(zip(amounts, dues), start=1):
        part_key = idempotency_key if index == 1 else f"{idempotency_key}:{index}"
        part_seu = (
            control
            if total == 1
            else seu_numero_for_installment(control, index, total)
        )
        charge = Charge.objects.create(
            tenant=tenant,
            idempotency_key=part_key,
            customer=customer,
            amount_cents=part_amount,
            due_date=part_due,
            description=description,
            seu_numero=part_seu,
            charge_kind=kind,
            message_lines=lines,
            schedule_group_id=group_id,
            installment_number=index if total > 1 else None,
            installment_count=total if total > 1 else None,
            num_dias_agenda=option_snap["num_dias_agenda"],
            multa_percent=multa,
            mora_percent_am=mora,
            nf_issue=nf_issue,
            status=Charge.Status.PENDING,
        )
        charge_options = {
            **option_snap,
            "message_lines": lines,
            "seu_numero": part_seu,
        }
        _register_one(
            charge=charge,
            gateway=gateway,
            idempotency_key=charge.idempotency_key,
            charge_options=charge_options,
        )
        charges.append(charge)

    return charges[0] if total == 1 else charges


@transaction.atomic
def emit_pending_charge(charge: Charge) -> Charge:
    """Emite no gateway uma cobrança já persistida sem gateway_ref (ex.: Admin antigo)."""
    if charge.gateway_ref:
        return charge
    if charge.status not in {Charge.Status.PENDING, Charge.Status.FAILED}:
        raise InvalidChargeInputError(
            f"Status {charge.status} não permite emissão no gateway"
        )
    try:
        validate_charge_amount_cents(charge.amount_cents)
    except ValueError as exc:
        raise InvalidChargeInputError(str(exc)) from exc

    from apps.billing.due_date_rules import validate_due_date

    try:
        validate_due_date(charge.due_date)
    except ValueError as exc:
        raise InvalidChargeInputError(str(exc)) from exc

    preset = get_billing_preset(tenant=charge.tenant)
    option_snap = resolve_charge_options_from_preset(preset)
    lines = charge.message_lines or split_message_lines(charge.description)
    if not charge.num_dias_agenda and option_snap.get("num_dias_agenda") is not None:
        charge.num_dias_agenda = option_snap["num_dias_agenda"]
    if charge.multa_percent is None and option_snap.get("multa_percent") is not None:
        charge.multa_percent = Decimal(str(option_snap["multa_percent"]))
    if charge.mora_percent_am is None and option_snap.get("mora_percent_am") is not None:
        charge.mora_percent_am = Decimal(str(option_snap["mora_percent_am"]))
    if not charge.message_lines:
        charge.message_lines = lines
    charge.status = Charge.Status.PENDING
    charge.save(
        update_fields=[
            "num_dias_agenda",
            "multa_percent",
            "mora_percent_am",
            "message_lines",
            "status",
            "updated_at",
        ]
    )

    seu = (charge.seu_numero or "").strip() or str(charge.id).replace("-", "")[:15]
    if not charge.seu_numero:
        charge.seu_numero = seu
        charge.save(update_fields=["seu_numero", "updated_at"])

    gateway = get_payment_gateway(tenant=charge.tenant)
    charge_options = {
        **option_snap,
        "message_lines": lines,
        "seu_numero": seu,
        "num_dias_agenda": charge.num_dias_agenda
        if charge.num_dias_agenda is not None
        else option_snap.get("num_dias_agenda"),
        "multa_percent": float(charge.multa_percent)
        if charge.multa_percent is not None
        else option_snap.get("multa_percent"),
        "mora_percent_am": float(charge.mora_percent_am)
        if charge.mora_percent_am is not None
        else option_snap.get("mora_percent_am"),
    }
    return _register_one(
        charge=charge,
        gateway=gateway,
        idempotency_key=charge.idempotency_key,
        charge_options=charge_options,
    )


@transaction.atomic
def cancel_charge(
    charge: Charge,
    *,
    motivo_cancelamento: str | None = None,
) -> Charge:
    """
    Cancela cobrança no gateway e no Hub.

    Regras:
    - paid → bloqueado
    - cancelled → idempotente
    - failed → bloqueado (sem boleto válido a cancelar)
    - pending / registered / overdue → permitido
    """
    if charge.status == Charge.Status.PAID:
        raise IncompatiblePaymentError("Cobrança paga não pode ser cancelada")
    if charge.status == Charge.Status.CANCELLED:
        return charge
    if charge.status == Charge.Status.FAILED:
        raise IncompatiblePaymentError(
            "Cobrança com falha de emissão não pode ser cancelada no banco"
        )
    if charge.status not in {
        Charge.Status.PENDING,
        Charge.Status.REGISTERED,
        Charge.Status.OVERDUE,
    }:
        raise IncompatiblePaymentError(
            f"Status {charge.status} não permite cancelamento"
        )

    motivo = (motivo_cancelamento or "").strip().upper() or None
    if motivo and motivo not in INTER_CANCEL_MOTIVOS:
        raise InvalidChargeInputError(
            f"motivo_cancelamento inválido. Use: {', '.join(sorted(INTER_CANCEL_MOTIVOS))}"
        )
    if not motivo:
        motivo = (
            getattr(settings, "INTER_CANCEL_MOTIVO", None) or "ACERTOS"
        ).strip().upper()

    if charge.gateway_ref:
        gateway = get_payment_gateway(tenant=charge.tenant)
        try:
            gateway.cancelar(ref=charge.gateway_ref, motivo_cancelamento=motivo)
        except PaymentGatewayError as exc:
            raise GatewayRegistrationError(str(exc)) from exc

    charge.status = Charge.Status.CANCELLED
    payload = dict(charge.gateway_payload or {})
    payload["motivo_cancelamento"] = motivo
    charge.gateway_payload = payload
    charge.save(update_fields=["status", "gateway_payload", "updated_at"])
    enqueue_outbox(
        tenant=charge.tenant,
        event_type="charge.cancelled",
        aggregate_type="charge",
        aggregate_id=charge.id,
        payload={
            "charge_id": str(charge.id),
            "gateway_ref": charge.gateway_ref,
            "motivo_cancelamento": motivo,
        },
        correlation_id=charge.correlation_id,
    )
    return charge


@transaction.atomic
def sync_charge_from_gateway(charge: Charge) -> Charge:
    """Consulta pagamento/situação no gateway e atualiza a cobrança no Hub."""
    if not charge.gateway_ref:
        raise ChargeNotFoundError("Cobrança sem gateway_ref para consulta")

    gateway = get_payment_gateway(tenant=charge.tenant)
    try:
        result = gateway.consultar_cobranca(ref=charge.gateway_ref)
    except PaymentGatewayError as exc:
        raise GatewayRegistrationError(str(exc)) from exc

    update_fields = _apply_boleto_result(
        charge, result, include_status=True, include_payload=True
    )
    update_fields.append("updated_at")
    charge.save(update_fields=list(dict.fromkeys(update_fields)))

    if charge.status == Charge.Status.PAID and not PaymentEvent.objects.filter(
        charge=charge
    ).exists():
        extras = result.extras or {}
        amount = extras.get("received_cents") or extras.get("amount_cents") or charge.amount_cents
        paid_raw = extras.get("data_situacao")
        paid_at = parse_datetime(str(paid_raw or "")) or timezone.now()
        if paid_at and timezone.is_naive(paid_at):
            paid_at = timezone.make_aware(paid_at, timezone.get_current_timezone())
        PaymentEvent.objects.create(
            tenant=charge.tenant,
            charge=charge,
            amount_cents=int(amount),
            paid_at=paid_at,
            gateway_ref=charge.gateway_ref,
            metadata={
                "provider": gateway.kind,
                "source": "sync_charge_from_gateway",
                "situacao": extras.get("situacao"),
            },
        )
        enqueue_outbox(
            tenant=charge.tenant,
            event_type="charge.paid",
            aggregate_type="charge",
            aggregate_id=charge.id,
            payload={"charge_id": str(charge.id), "source": "sync"},
            correlation_id=charge.correlation_id,
        )

    try:
        ensure_charge_pdf(charge)
    except Exception:
        pass

    return charge


def _persist_boleto_pdf(*, tenant, charge_id, pdf_bytes: bytes) -> StoredFile | None:
    if not pdf_bytes:
        return None
    object_key = f"billing/{tenant.id}/charges/{charge_id}/{uuid4().hex[:12]}.pdf"
    storage = get_storage()
    storage.put(key=object_key, data=pdf_bytes, content_type="application/pdf")
    return StoredFile.objects.create(
        tenant=tenant,
        backend=StoredFile.Backend.LOCAL,
        object_key=object_key,
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
        checksum_sha256=StoredFile.checksum(pdf_bytes),
        encryption="none",
        purpose="boleto_pdf",
    )


@transaction.atomic
def ensure_charge_pdf(charge: Charge) -> Charge:
    """Baixa PDF no gateway e persiste StoredFile (idempotente)."""
    charge = Charge.objects.select_for_update().get(pk=charge.pk)
    if charge.pdf_file_id:
        return charge
    if not charge.gateway_ref:
        raise ChargeNotFoundError("Cobrança sem gateway_ref para PDF")

    gateway = get_payment_gateway(tenant=charge.tenant)
    try:
        pdf_bytes = gateway.baixar_pdf(ref=charge.gateway_ref)
    except PaymentGatewayError as exc:
        raise GatewayRegistrationError(str(exc)) from exc
    if not isinstance(pdf_bytes, (bytes, bytearray)) or not pdf_bytes.startswith(
        b"%PDF"
    ):
        raise GatewayRegistrationError("Resposta do gateway não é um PDF válido")

    stored = _persist_boleto_pdf(
        tenant=charge.tenant, charge_id=charge.id, pdf_bytes=pdf_bytes
    )
    if stored is None:
        raise GatewayRegistrationError("Falha ao persistir PDF do boleto")
    charge.pdf_file = stored
    charge.save(update_fields=["pdf_file", "updated_at"])
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

    try:
        canonical = normalize_gateway_payload(payload)
    except ValueError as exc:
        raise InvalidChargeInputError(str(exc)) from exc
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

    gateway_ref = (canonical.get("gateway_ref") or "").strip()
    external_reference = canonical.get("external_reference") or ""
    charge = None
    if gateway_ref:
        matches = list(
            Charge.objects.filter(gateway_ref=gateway_ref).select_related("tenant")[:2]
        )
        if len(matches) > 1:
            raise ChargeNotFoundError(
                "gateway_ref ambíguo entre tenants — informe tenant_slug"
            )
        charge = matches[0] if matches else None
    if charge is None and external_reference:
        # Apenas UUID de charge (nunca seu_numero global — risco de colisão/IDOR).
        try:
            charge_id = uuid.UUID(str(external_reference))
        except (ValueError, TypeError) as exc:
            raise ChargeNotFoundError(
                "tenant_slug ausente: use gateway_ref ou external_reference=charge.id"
            ) from exc
        charge = (
            Charge.objects.filter(id=charge_id).select_related("tenant").first()
        )
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


def _find_charge_for_webhook(inbox: WebhookInbox, payload: dict) -> Charge | None:
    gateway_ref = payload.get("gateway_ref")
    if gateway_ref:
        charge = (
            Charge.objects.select_for_update()
            .filter(tenant=inbox.tenant, gateway_ref=gateway_ref)
            .first()
        )
        if charge:
            return charge
    ext = payload.get("external_reference")
    if not ext:
        return None
    charge = (
        Charge.objects.select_for_update()
        .filter(tenant=inbox.tenant, id=ext)
        .first()
    )
    if charge:
        return charge
    return (
        Charge.objects.select_for_update()
        .filter(tenant=inbox.tenant, seu_numero=str(ext))
        .first()
    )


def _enrich_webhook_from_gateway(inbox: WebhookInbox, charge: Charge, payload: dict) -> dict:
    """GET detalhe Inter quando o callback é leve ou falta valor no RECEBIDO."""
    if not payload.get("needs_enrich"):
        return payload
    ref = charge.gateway_ref or payload.get("gateway_ref")
    if not ref:
        return payload

    gateway = get_payment_gateway(tenant=inbox.tenant)
    try:
        result = gateway.consultar_cobranca(ref=ref)
    except PaymentGatewayError as exc:
        inbox.status = WebhookInbox.Status.FAILED
        inbox.error_message = f"Falha ao enriquecer webhook: {exc}"
        inbox.save(update_fields=["status", "error_message", "updated_at"])
        return payload

    fields = _apply_boleto_result(
        charge, result, include_status=True, include_payload=True
    )
    if fields:
        charge.save(update_fields=list(dict.fromkeys([*fields, "updated_at"])))

    extras = result.extras or {}
    situacao = (extras.get("situacao") or "").strip().upper()
    amount = extras.get("received_cents")
    if amount is None:
        amount = extras.get("amount_cents")
    if amount is None:
        amount = charge.amount_cents

    out = dict(payload)
    out["needs_enrich"] = False
    out["gateway_ref"] = charge.gateway_ref or ref
    out["amount_cents"] = int(amount)
    if situacao:
        out["situacao"] = situacao
        out["event"] = situacao
        hub = map_inter_situacao(situacao)
        if hub:
            out["hub_status"] = hub
    paid_raw = extras.get("data_situacao") or out.get("paid_at")
    paid_at = parse_datetime(str(paid_raw or "")) or timezone.now()
    if timezone.is_naive(paid_at):
        paid_at = timezone.make_aware(paid_at, timezone.get_current_timezone())
    out["paid_at"] = paid_at.isoformat()

    inbox.raw_payload = out
    inbox.save(update_fields=["raw_payload", "updated_at"])
    return out


def _webhook_is_payment(payload: dict) -> bool:
    hub_status = payload.get("hub_status")
    if hub_status:
        return hub_status == Charge.Status.PAID
    # Canônico / Asaas sem hub_status: trata como pagamento (contrato legado).
    return True


@transaction.atomic
def process_webhook_inbox(inbox: WebhookInbox) -> WebhookInbox:
    if inbox.status == WebhookInbox.Status.PROCESSED:
        return inbox
    if not inbox.signature_valid:
        raise InvalidWebhookSignatureError("Inbox sem assinatura válida")

    inbox.status = WebhookInbox.Status.PROCESSING
    inbox.save(update_fields=["status", "updated_at"])

    payload = dict(inbox.raw_payload or {})
    charge = _find_charge_for_webhook(inbox, payload)
    if charge is None:
        inbox.status = WebhookInbox.Status.FAILED
        inbox.error_message = "Cobrança não encontrada"
        inbox.save(update_fields=["status", "error_message", "updated_at"])
        return inbox

    payload = _enrich_webhook_from_gateway(inbox, charge, payload)
    if inbox.status == WebhookInbox.Status.FAILED:
        return inbox

    if not _webhook_is_payment(payload):
        # Callback Inter de ciclo de vida (A_RECEBER, CANCELADO, …): sem PaymentEvent.
        new_status = payload.get("hub_status")
        if new_status and charge.status != Charge.Status.PAID and new_status != charge.status:
            if not (
                charge.status == Charge.Status.CANCELLED
                and new_status != Charge.Status.CANCELLED
            ):
                charge.status = new_status
                charge.save(update_fields=["status", "updated_at"])
        inbox.status = WebhookInbox.Status.PROCESSED
        inbox.processed_at = timezone.now()
        inbox.error_message = ""
        inbox.save(
            update_fields=["status", "processed_at", "error_message", "updated_at"]
        )
        return inbox

    amount_raw = payload.get("amount_cents")
    if amount_raw is None:
        inbox.status = WebhookInbox.Status.FAILED
        inbox.error_message = "Valor ausente no webhook"
        inbox.save(update_fields=["status", "error_message", "updated_at"])
        return inbox
    amount_cents = int(amount_raw)
    paid_at = parse_datetime(str(payload.get("paid_at") or "")) or timezone.now()
    if timezone.is_naive(paid_at):
        paid_at = timezone.make_aware(paid_at, timezone.get_current_timezone())
    gateway_ref = payload.get("gateway_ref") or charge.gateway_ref

    if amount_cents != charge.amount_cents:
        inbox.status = WebhookInbox.Status.FAILED
        inbox.error_message = "Valor incompatível"
        inbox.save(update_fields=["status", "error_message", "updated_at"])
        return inbox

    # Anti-replay: um PaymentEvent por cobrança (mesmo com novo idempotency_key).
    existing_event = PaymentEvent.objects.filter(charge=charge).first()
    if existing_event is None and not PaymentEvent.objects.filter(
        webhook_inbox=inbox
    ).exists():
        PaymentEvent.objects.create(
            tenant=inbox.tenant,
            charge=charge,
            webhook_inbox=inbox,
            amount_cents=amount_cents,
            paid_at=paid_at,
            gateway_ref=gateway_ref,
            metadata={
                "provider": inbox.provider,
                "situacao": payload.get("situacao") or payload.get("event") or "",
            },
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
