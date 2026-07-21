import uuid

from django.db import models

from shared.models import UUIDPrimaryKeyModel
from shared.tenancy import TenantOwnedModel


class NfIssue(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PENDING_TAX = "pending_tax", "Imposto pendente"
        QUEUED = "queued", "Na fila"
        SUBMITTING = "submitting", "Enviando"
        POLLING = "polling", "Consultando"
        AUTHORIZED = "authorized", "Autorizada"
        REJECTED = "rejected", "Rejeitada"
        CANCELLED = "cancelled", "Cancelada"
        FAILED = "failed", "Falhou"

    idempotency_key = models.CharField(max_length=128, verbose_name="Chave de idempotência")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Status",
    )
    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="nf_issues",
        verbose_name="Prestador",
    )
    customer = models.ForeignKey(
        "master_data.Customer",
        on_delete=models.PROTECT,
        related_name="nf_issues",
        verbose_name="Tomador",
    )
    service = models.ForeignKey(
        "master_data.ServiceCatalogItem",
        on_delete=models.PROTECT,
        related_name="nf_issues",
        verbose_name="Serviço",
    )
    fiscal_profile = models.ForeignKey(
        "fiscal.FiscalProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="nf_issues",
        verbose_name="Perfil fiscal",
    )
    ibge_code = models.CharField(max_length=7, verbose_name="Código IBGE")
    competence_date = models.DateField(verbose_name="Data de competência")
    amount_cents = models.BigIntegerField(verbose_name="Valor")
    resolved_rule = models.ForeignKey(
        "fiscal.MunicipalTaxRule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Regra resolvida",
    )
    resolved_params = models.JSONField(
        null=True, blank=True, verbose_name="Parâmetros resolvidos"
    )
    internal_payload = models.JSONField(
        null=True, blank=True, verbose_name="Payload interno"
    )
    focus_status_raw = models.JSONField(
        null=True, blank=True, verbose_name="Status bruto Focus"
    )
    focus_ref = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Referência Focus"
    )
    payload_hash = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Hash do payload"
    )
    correlation_id = models.UUIDField(
        default=uuid.uuid4, verbose_name="ID de correlação"
    )
    rejection_code = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Código de rejeição"
    )

    class Meta:
        verbose_name = "Emissão NFS-e"
        verbose_name_plural = "Emissões NFS-e"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_nf_issue_tenant_idempotency",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_cents__gt=0),
                name="ck_nf_issue_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"]),
            models.Index(fields=["tenant", "competence_date"]),
            models.Index(fields=["tenant", "correlation_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.idempotency_key} — {self.get_status_display()}"


class NfArtifact(TenantOwnedModel):
    class Kind(models.TextChoices):
        XML = "xml", "XML"
        PDF = "pdf", "PDF"

    nf_issue = models.ForeignKey(
        NfIssue,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    stored_file = models.ForeignKey(
        "ops.StoredFile",
        on_delete=models.PROTECT,
        related_name="nf_artifacts",
    )
    checksum_sha256 = models.CharField(max_length=64)

    class Meta:
        verbose_name = "Artefato NFS-e"
        verbose_name_plural = "Artefatos NFS-e"
        constraints = [
            models.UniqueConstraint(
                fields=["nf_issue", "kind"],
                name="uq_nf_artifact_issue_kind",
            )
        ]


class FiscalRuleSnapshot(TenantOwnedModel):
    nf_issue = models.OneToOneField(
        NfIssue,
        on_delete=models.CASCADE,
        related_name="rule_snapshot",
    )
    source_rule_id = models.UUIDField(null=True, blank=True)
    catalog_version = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Snapshot da regra fiscal"
        verbose_name_plural = "Snapshots da regra fiscal"


class NfIssueEvent(UUIDPrimaryKeyModel):
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.PROTECT,
        related_name="nf_issue_events",
        verbose_name="Tenant",
    )
    nf_issue = models.ForeignKey(
        NfIssue,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="Emissão NFS-e",
    )
    from_status = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="Status de origem",
    )
    to_status = models.CharField(
        max_length=32,
        verbose_name="Status de destino",
    )
    actor = models.CharField(
        max_length=64,
        default="system",
        verbose_name="Ator",
    )
    metadata = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Metadados",
    )
    occurred_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Ocorrido em",
    )

    class Meta:
        verbose_name = "Evento de emissão"
        verbose_name_plural = "Eventos de emissão"
        indexes = [models.Index(fields=["nf_issue", "occurred_at"])]
        ordering = ("occurred_at",)

    def __str__(self) -> str:
        return f"{self.from_status or '—'} → {self.to_status}"
