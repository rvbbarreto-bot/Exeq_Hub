from django.db import models
from django.utils import timezone

from shared.tenancy import TenantOwnedModel


class ChannelSession(TenantOwnedModel):
    class Status(models.TextChoices):
        COLLECTING = "collecting", "Coletando"
        READY_TO_CONFIRM = "ready_to_confirm", "Pronta para confirmar"
        EMITTED = "emitted", "Emitida"
        EXPIRED = "expired", "Expirada"
        CANCELLED = "cancelled", "Cancelada"

    idempotency_key = models.CharField(max_length=128, verbose_name="Chave de idempotência")
    phone_e164 = models.CharField(max_length=20, verbose_name="Telefone (E.164)")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.COLLECTING,
        verbose_name="Status",
    )
    draft_payload = models.JSONField(
        default=dict, blank=True, verbose_name="Rascunho"
    )
    nf_issue = models.ForeignKey(
        "issuance.NfIssue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="channel_sessions",
        verbose_name="Emissão NFS-e",
    )
    last_message_at = models.DateTimeField(
        default=timezone.now, verbose_name="Última mensagem em"
    )

    class Meta:
        verbose_name = "Sessão do canal"
        verbose_name_plural = "Sessões do canal"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_channel_session_tenant_idempotency",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "phone_e164", "status"]),
        ]


class ChannelNotification(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SENT = "sent", "Enviada"
        FAILED = "failed", "Falhou"

    session = models.ForeignKey(
        ChannelSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    nf_issue = models.ForeignKey(
        "issuance.NfIssue",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="channel_notifications",
    )
    phone_e164 = models.CharField(max_length=20, verbose_name="Telefone (E.164)")
    event_type = models.CharField(max_length=64, verbose_name="Tipo de evento")
    message_body = models.TextField(verbose_name="Mensagem")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    provider_ref = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Referência do provedor"
    )

    class Meta:
        verbose_name = "Notificação do canal"
        verbose_name_plural = "Notificações do canal"
