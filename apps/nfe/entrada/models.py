"""Models NF-e de entrada — cursor NSU, documentos recebidos, manifestação."""

from __future__ import annotations

import uuid

from django.db import models

from shared.models import UUIDPrimaryKeyModel
from shared.tenancy import TenantOwnedModel


class NfeDistribuicaoCursor(TenantOwnedModel):
    """Controle persistente de NSU por CNPJ destinatário (NT 2014.002)."""

    class Environment(models.TextChoices):
        PRODUCTION = "1", "Produção"
        HOMOLOG = "2", "Homologação"

    provider = models.OneToOneField(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="nfe_distribuicao_cursor",
        verbose_name="Empresa",
    )
    cnpj = models.CharField(max_length=14, verbose_name="CNPJ")
    ult_nsu = models.CharField(max_length=15, default="0", verbose_name="Último NSU")
    max_nsu = models.CharField(max_length=15, default="0", verbose_name="Max NSU")
    last_query_at = models.DateTimeField(null=True, blank=True, verbose_name="Última consulta")
    last_c_stat = models.CharField(max_length=3, blank=True, default="", verbose_name="cStat")
    last_x_motivo = models.TextField(blank=True, default="", verbose_name="xMotivo")
    blocked_until = models.DateTimeField(null=True, blank=True, verbose_name="Bloqueado até")
    automatic_enabled = models.BooleanField(default=False, verbose_name="Consulta automática")
    interval_seconds = models.PositiveIntegerField(
        default=3600,
        verbose_name="Intervalo (s)",
    )
    tp_amb = models.CharField(
        max_length=1,
        choices=Environment.choices,
        default=Environment.HOMOLOG,
        verbose_name="Ambiente",
    )

    class Meta:
        verbose_name = "Cursor distribuição NF-e"
        verbose_name_plural = "Cursors distribuição NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider"],
                name="uq_nfe_dist_cursor_tenant_provider",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "cnpj"]),
            models.Index(fields=["tenant", "automatic_enabled"]),
        ]

    def __str__(self) -> str:
        return f"NSU {self.cnpj} ult={self.ult_nsu}"


class NfeEntradaDocument(TenantOwnedModel):
    """Documento fiscal recebido via NFeDistribuicaoDFe."""

    class SchemaType(models.TextChoices):
        RES_NFE = "resNFe", "Resumo NF-e"
        PROC_NFE = "procNFe", "NF-e processada"
        RES_EVENTO = "resEvento", "Resumo evento"
        PROC_EVENTO = "procEventoNFe", "Evento processado"
        OTHER = "other", "Outro"

    class XmlStatus(models.TextChoices):
        PENDING = "pending", "XML pendente"
        AVAILABLE = "available", "XML disponível"
        ERROR = "error", "Erro"

    class ManifestStatus(models.TextChoices):
        NONE = "none", "Sem manifestação"
        CIENCIA = "ciencia", "Ciência"
        CONFIRMADA = "confirmada", "Confirmada"
        DESCONHECIDA = "desconhecida", "Desconhecida"
        NAO_REALIZADA = "nao_realizada", "Operação não realizada"

    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="nfe_entrada_documents",
        verbose_name="Empresa destinatária",
    )
    nsu = models.CharField(max_length=15, verbose_name="NSU")
    schema_type = models.CharField(
        max_length=20,
        choices=SchemaType.choices,
        verbose_name="Tipo schema",
    )
    access_key = models.CharField(max_length=44, blank=True, default="", verbose_name="Chave")
    issuer_cnpj = models.CharField(max_length=14, blank=True, default="", verbose_name="CNPJ emitente")
    issuer_name = models.CharField(max_length=120, blank=True, default="", verbose_name="Emitente")
    recipient_cnpj = models.CharField(max_length=14, blank=True, default="", verbose_name="CNPJ destinatário")
    number = models.PositiveIntegerField(null=True, blank=True, verbose_name="Número")
    series = models.PositiveIntegerField(null=True, blank=True, verbose_name="Série")
    issue_date = models.DateField(null=True, blank=True, verbose_name="Data emissão")
    total_cents = models.BigIntegerField(null=True, blank=True, verbose_name="Valor (centavos)")
    nfe_status = models.CharField(max_length=32, blank=True, default="", verbose_name="Situação NF-e")
    xml_status = models.CharField(
        max_length=16,
        choices=XmlStatus.choices,
        default=XmlStatus.PENDING,
        verbose_name="Status XML",
    )
    manifest_status = models.CharField(
        max_length=20,
        choices=ManifestStatus.choices,
        default=ManifestStatus.NONE,
        verbose_name="Manifestação",
    )
    xml_hash = models.CharField(max_length=64, blank=True, default="", verbose_name="Hash SHA-256")
    stored_file = models.ForeignKey(
        "ops.StoredFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nfe_entrada_documents",
        verbose_name="Arquivo XML",
    )
    raw_metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadados")

    class Meta:
        verbose_name = "NF-e de entrada"
        verbose_name_plural = "NF-e de entrada"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "nsu"],
                name="uq_nfe_entrada_tenant_provider_nsu",
            ),
            models.UniqueConstraint(
                fields=["tenant", "access_key"],
                condition=models.Q(access_key__gt=""),
                name="uq_nfe_entrada_tenant_access_key",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "-issue_date"]),
            models.Index(fields=["tenant", "manifest_status"]),
            models.Index(fields=["tenant", "xml_status"]),
            models.Index(fields=["tenant", "issuer_cnpj"]),
            models.Index(fields=["tenant", "access_key"]),
        ]

    def __str__(self) -> str:
        return f"Entrada {self.access_key or self.nsu} ({self.schema_type})"


class NfeEntradaManifestation(TenantOwnedModel):
    """Manifestação do destinatário (eventos 2102xx)."""

    class EventType(models.TextChoices):
        CIENCIA = "210210", "Ciência da Emissão"
        CONFIRMACAO = "210200", "Confirmação da Operação"
        DESCONHECIMENTO = "210220", "Desconhecimento"
        OPERACAO_NAO_REALIZADA = "210240", "Operação não Realizada"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        ACCEPTED = "accepted", "Homologado"
        REJECTED = "rejected", "Rejeitado"

    document = models.ForeignKey(
        NfeEntradaDocument,
        on_delete=models.CASCADE,
        related_name="manifestations",
        verbose_name="Documento",
    )
    tp_evento = models.CharField(max_length=6, choices=EventType.choices, verbose_name="tpEvento")
    n_seq = models.PositiveSmallIntegerField(default=1, verbose_name="nSeqEvento")
    protocol = models.CharField(max_length=60, blank=True, default="", verbose_name="Protocolo")
    c_stat = models.CharField(max_length=8, blank=True, default="", verbose_name="cStat")
    x_motivo = models.CharField(max_length=512, blank=True, default="", verbose_name="xMotivo")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    actor_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nfe_entrada_manifestations",
        verbose_name="Usuário",
    )
    actor_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP")
    stored_file = models.ForeignKey(
        "ops.StoredFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nfe_entrada_manifestations",
        verbose_name="XML evento",
    )
    correlation_id = models.UUIDField(default=uuid.uuid4, verbose_name="Correlação")

    class Meta:
        verbose_name = "Manifestação NF-e entrada"
        verbose_name_plural = "Manifestações NF-e entrada"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "document", "tp_evento", "n_seq"],
                condition=models.Q(status="accepted"),
                name="uq_nfe_entrada_manifest_accepted",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "document"]),
            models.Index(fields=["tenant", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.tp_evento} · {self.status}"


class NfeDistribuicaoSyncLog(TenantOwnedModel):
    """Auditoria por consulta distNSU."""

    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="nfe_distribuicao_sync_logs",
        verbose_name="Empresa",
    )
    cnpj = models.CharField(max_length=14, verbose_name="CNPJ")
    ult_nsu_before = models.CharField(max_length=15, verbose_name="ultNSU antes")
    ult_nsu_after = models.CharField(max_length=15, blank=True, default="", verbose_name="ultNSU depois")
    max_nsu = models.CharField(max_length=15, blank=True, default="", verbose_name="maxNSU")
    c_stat = models.CharField(max_length=3, blank=True, default="", verbose_name="cStat")
    x_motivo = models.TextField(blank=True, default="", verbose_name="xMotivo")
    documents_count = models.PositiveIntegerField(default=0, verbose_name="Documentos")
    duration_ms = models.PositiveIntegerField(null=True, blank=True, verbose_name="Duração ms")
    correlation_id = models.UUIDField(default=uuid.uuid4, verbose_name="Correlação")
    actor = models.CharField(max_length=64, default="system", verbose_name="Ator")
    success = models.BooleanField(default=False, verbose_name="Sucesso")
    error_message = models.TextField(blank=True, default="", verbose_name="Erro")

    class Meta:
        verbose_name = "Log sync distribuição NF-e"
        verbose_name_plural = "Logs sync distribuição NF-e"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["tenant", "provider", "-created_at"]),
            models.Index(fields=["tenant", "correlation_id"]),
        ]

    def __str__(self) -> str:
        return f"sync {self.cnpj} cStat={self.c_stat}"
