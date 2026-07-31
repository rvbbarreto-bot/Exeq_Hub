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

    class ChargeKind(models.TextChoices):
        SIMPLE = "simple", "Pagamento único"
        INSTALLMENT = "installment", "Parcelado"
        RECURRING = "recurring", "Recorrente"

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
    amount_cents = models.BigIntegerField(verbose_name="Valor")
    due_date = models.DateField(verbose_name="Vencimento")
    description = models.TextField(blank=True, default="", verbose_name="Descrição")
    seu_numero = models.CharField(
        max_length=15,
        blank=True,
        default="",
        verbose_name="Código de controle",
    )
    charge_kind = models.CharField(
        max_length=16,
        choices=ChargeKind.choices,
        default=ChargeKind.SIMPLE,
        verbose_name="Tipo de emissão",
    )
    message_lines = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Linhas da descrição (boleto)",
    )
    schedule_group_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name="Grupo da agenda",
    )
    installment_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Parcela",
    )
    installment_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Total de parcelas",
    )
    num_dias_agenda = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Dias após vencimento",
    )
    multa_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Multa %",
    )
    mora_percent_am = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Juros % a.m.",
    )
    gateway_ref = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Referência gateway"
    )
    billing_type = models.CharField(
        max_length=32,
        blank=True,
        default="BOLETO",
        verbose_name="Tipo de cobrança",
    )
    payment_url = models.URLField(
        max_length=512, blank=True, default="", verbose_name="URL do boleto"
    )
    digitable_line = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Linha digitável"
    )
    barcode = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Código de barras"
    )
    boleto_pdf_url = models.URLField(
        max_length=512, blank=True, default="", verbose_name="URL PDF do boleto"
    )
    pix_copy_paste = models.TextField(
        blank=True, default="", verbose_name="PIX copia e cola"
    )
    pdf_file = models.ForeignKey(
        "ops.StoredFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges",
        verbose_name="PDF do boleto",
    )
    gateway_payload = models.JSONField(
        null=True, blank=True, verbose_name="Payload do gateway"
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
            models.Index(fields=["tenant", "schedule_group_id"]),
            models.Index(fields=["tenant", "seu_numero"]),
        ]


class WebhookInbox(TenantOwnedModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "Recebido"
        PROCESSING = "processing", "Processando"
        PROCESSED = "processed", "Processado"
        FAILED = "failed", "Falhou"

    class Provider(models.TextChoices):
        INTER = "inter", "Inter"
        ASAAS = "asaas", "Asaas"
        C6 = "c6", "C6"

    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
        default=Provider.INTER,
        verbose_name="Provedor",
    )
    idempotency_key = models.CharField(
        max_length=128, verbose_name="Chave de idempotência"
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RECEIVED,
        verbose_name="Status",
    )
    signature = models.CharField(
        max_length=256, blank=True, default="", verbose_name="Assinatura"
    )
    signature_valid = models.BooleanField(
        default=False, verbose_name="Assinatura válida"
    )
    raw_payload = models.JSONField(default=dict, verbose_name="Payload bruto")
    payload_hash = models.CharField(max_length=64, verbose_name="Hash do payload")
    error_message = models.TextField(
        blank=True, default="", verbose_name="Mensagem de erro"
    )
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Processado em"
    )

    class Meta:
        verbose_name = "Caixa de entrada de webhook"
        verbose_name_plural = "Caixas de entrada de webhook"
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
        verbose_name="Tenant",
    )
    charge = models.ForeignKey(
        Charge,
        on_delete=models.PROTECT,
        related_name="payment_events",
        verbose_name="Cobrança",
    )
    webhook_inbox = models.ForeignKey(
        WebhookInbox,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_events",
        verbose_name="Caixa de entrada de webhook",
    )
    amount_cents = models.BigIntegerField(verbose_name="Valor")
    paid_at = models.DateTimeField(verbose_name="Pago em")
    gateway_ref = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Referência gateway"
    )
    metadata = models.JSONField(null=True, blank=True, verbose_name="Metadados")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")

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


class PaymentProviderAudit(UUIDPrimaryKeyModel):
    """
    Trilha de auditoria para troca de credenciais/provedor de cobrança.

    Escolha: modelo próprio (não reusa CertificateAudit), porque CertificateAudit
    exige FK obrigatória para DigitalCertificate (A1 PFX). PaymentAccount
    (múltiplas contas) fica fora desta entrega.
    """

    class Action(models.TextChoices):
        PROVIDER_CHANGED = "provider_changed", "Provedor alterado"
        CREDENTIALS_UPDATED = "credentials_updated", "Credenciais atualizadas"
        CONNECTION_TESTED = "connection_tested", "Conexão testada"
        WEBHOOK_CONFIGURED = "webhook_configured", "Webhook configurado"
        WEBHOOK_RETRY = "webhook_retry", "Retry de callbacks"

    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.PROTECT,
        related_name="payment_provider_audits",
        verbose_name="Tenant",
    )
    provider = models.CharField(max_length=32, verbose_name="Provedor")
    action = models.CharField(max_length=64, verbose_name="Ação")
    actor_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Usuário",
    )
    metadata = models.JSONField(
        default=dict, blank=True, verbose_name="Metadados"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")

    class Meta:
        verbose_name = "Auditoria de provedor de cobrança"
        verbose_name_plural = "Auditorias de provedor de cobrança"
        indexes = [
            models.Index(fields=["tenant", "provider", "created_at"]),
        ]
