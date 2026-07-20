import hashlib
import uuid

from django.db import models

from shared.models import UUIDPrimaryKeyModel
from shared.tenancy import TenantOwnedModel


class Charge(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        REGISTERED = "registered", "Registrada"
        PAID = "paid", "Paga"
        OVERDUE = "overdue", "Vencida"
        CANCELLED = "cancelled", "Cancelada"
        FAILED = "failed", "Falhou"

    idempotency_key = models.CharField(max_length=128, verbose_name="Chave de idempotência")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    customer = models.ForeignKey(
        "master_data.Customer",
        on_delete=models.PROTECT,
        related_name="charges",
        verbose_name="Tomador",
    )
    amount_cents = models.BigIntegerField(verbose_name="Valor (centavos)")
    due_date = models.DateField(verbose_name="Vencimento")
    description = models.TextField(blank=True, default="", verbose_name="Descrição")
    gateway_ref = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Referência gateway"
    )
    nf_issue = models.ForeignKey(
        "issuance.NfIssue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges",
        verbose_name="Emissão NFS-e",
    )
    correlation_id = models.UUIDField(
        default=uuid.uuid4, verbose_name="ID de correlação"
    )

    class Meta:
        verbose_name = "Cobrança"
        verbose_name_plural = "Cobranças"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_charge_tenant_idempotency",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_cents__gt=0),
                name="ck_charge_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "due_date"]),
            models.Index(fields=["tenant", "gateway_ref"]),
        ]


class WebhookInbox(TenantOwnedModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "Recebido"
        PROCESSING = "processing", "Processando"
        PROCESSED = "processed", "Processado"
        FAILED = "failed", "Falhou"

    provider = models.CharField(max_length=32, default="asaas")
    idempotency_key = models.CharField(max_length=128)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RECEIVED,
    )
    signature = models.CharField(max_length=256, blank=True, default="")
    signature_valid = models.BooleanField(default=False)
    raw_payload = models.JSONField(default=dict)
    payload_hash = models.CharField(max_length=64)
    error_message = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Inbox de webhook"
        verbose_name_plural = "Inboxes de webhook"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "idempotency_key"],
                name="uq_webhook_inbox_tenant_provider_key",
            )
        ]

    @staticmethod
    def hash_payload(payload: dict) -> str:
        import json

        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


class PaymentEvent(UUIDPrimaryKeyModel):
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.PROTECT,
        related_name="payment_events",
    )
    charge = models.ForeignKey(
        Charge,
        on_delete=models.PROTECT,
        related_name="payment_events",
    )
    webhook_inbox = models.ForeignKey(
        WebhookInbox,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_events",
    )
    amount_cents = models.BigIntegerField()
    paid_at = models.DateTimeField()
    gateway_ref = models.CharField(max_length=128, blank=True, default="")
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento de pagamento"
        verbose_name_plural = "Eventos de pagamento"
        indexes = [models.Index(fields=["charge", "paid_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_cents__gt=0),
                name="ck_payment_event_amount_positive",
            )
        ]
