"""Domínio NF-e modelo 55 — greenfield (ADR-NFE-001). Separado de NfIssue (NFS-e)."""

from __future__ import annotations

import uuid

from django.db import models

from shared.models import UUIDPrimaryKeyModel
from shared.tenancy import TenantOwnedModel


class NfeProduct(TenantOwnedModel):
    """SKU fiscal sem estoque (LLR UI T4)."""

    code = models.CharField(max_length=60, verbose_name="Código")
    description = models.CharField(max_length=120, verbose_name="Descrição")
    unit = models.CharField(max_length=6, default="UN", verbose_name="Unidade")
    unit_price_cents = models.BigIntegerField(default=0, verbose_name="Preço unitário (centavos)")
    ncm = models.CharField(max_length=8, verbose_name="NCM")
    origin = models.CharField(max_length=1, default="0", verbose_name="Origem")
    cfop_internal = models.CharField(max_length=4, default="5102", verbose_name="CFOP interno")
    cfop_interstate = models.CharField(
        max_length=4, blank=True, default="6102", verbose_name="CFOP interestadual"
    )
    csosn = models.CharField(max_length=3, blank=True, default="", verbose_name="CSOSN")
    icms_cst = models.CharField(max_length=3, blank=True, default="", verbose_name="CST ICMS")
    icms_rate_bp = models.PositiveIntegerField(
        default=0, verbose_name="Alíquota ICMS (basis points, 1800=18%)"
    )
    pis_cst = models.CharField(max_length=2, default="07", verbose_name="CST PIS")
    pis_rate_bp = models.PositiveIntegerField(default=0, verbose_name="Alíquota PIS bp")
    cofins_cst = models.CharField(max_length=2, default="07", verbose_name="CST COFINS")
    cofins_rate_bp = models.PositiveIntegerField(default=0, verbose_name="Alíquota COFINS bp")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Produto fiscal NF-e"
        verbose_name_plural = "Produtos fiscais NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="uq_nfe_product_tenant_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.description}"


class NfeNumberSeries(TenantOwnedModel):
    """Série + próximo número por emitente e ambiente (D-06)."""

    class Environment(models.TextChoices):
        HOMOLOG = "2", "Homologação"
        PRODUCTION = "1", "Produção"

    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="nfe_number_series",
        verbose_name="Emitente",
    )
    series = models.PositiveIntegerField(default=1, verbose_name="Série")
    tp_amb = models.CharField(
        max_length=1,
        choices=Environment.choices,
        default=Environment.HOMOLOG,
        verbose_name="Ambiente",
    )
    next_number = models.PositiveIntegerField(default=1, verbose_name="Próximo número")
    is_active = models.BooleanField(default=True, verbose_name="Ativa")

    class Meta:
        verbose_name = "Série NF-e"
        verbose_name_plural = "Séries NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "series", "tp_amb"],
                name="uq_nfe_series_provider_serie_amb",
            ),
        ]

    def __str__(self) -> str:
        return f"S{self.series}/{self.tp_amb} next={self.next_number}"


class NfeInvoice(TenantOwnedModel):
    """Documento NF-e: draft → … → authorized (FSM LLR)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        QUEUED = "queued", "Na fila"
        SUBMITTING = "submitting", "Enviando"
        POLLING = "polling", "Consultando"
        AUTHORIZED = "authorized", "Autorizada"
        REJECTED = "rejected", "Rejeitada"
        FAILED = "failed", "Falhou"
        CANCEL_REQUESTED = "cancel_requested", "Cancelamento pendente"
        CANCELLED = "cancelled", "Cancelada"

    idempotency_key = models.CharField(max_length=128, verbose_name="Chave de idempotência")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Status",
    )
    version = models.PositiveIntegerField(default=1, verbose_name="Versão otimista")
    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="nfe_invoices",
        verbose_name="Emitente",
    )
    customer = models.ForeignKey(
        "master_data.Customer",
        on_delete=models.PROTECT,
        related_name="nfe_invoices",
        verbose_name="Destinatário",
    )
    nature_operation = models.CharField(
        max_length=60, default="VENDA", verbose_name="Natureza da operação"
    )
    finality = models.CharField(max_length=1, default="1", verbose_name="Finalidade")
    consumer_final = models.BooleanField(default=False, verbose_name="Consumidor final")
    buyer_presence = models.CharField(max_length=1, default="9", verbose_name="Presença comprador")
    ind_ie_dest = models.CharField(max_length=1, default="9", verbose_name="indIEDest")
    series = models.PositiveIntegerField(default=1, verbose_name="Série")
    number = models.PositiveIntegerField(null=True, blank=True, verbose_name="Número")
    tp_amb = models.CharField(max_length=1, default="2", verbose_name="Ambiente")
    issue_date = models.DateField(verbose_name="Data de emissão")
    freight_mod = models.CharField(max_length=1, default="9", verbose_name="Modalidade frete")
    freight_cents = models.BigIntegerField(default=0, verbose_name="Frete (centavos)")
    discount_cents = models.BigIntegerField(default=0, verbose_name="Desconto (centavos)")
    payment_method = models.CharField(max_length=2, default="99", verbose_name="Forma pag. tPag")
    payment_amount_cents = models.BigIntegerField(null=True, blank=True, verbose_name="Valor pag.")
    total_cents = models.BigIntegerField(default=0, verbose_name="Total (centavos)")
    fiscal_snapshot = models.JSONField(null=True, blank=True, verbose_name="Snapshot fiscal")
    taxes_summary = models.JSONField(null=True, blank=True, verbose_name="Totais impostos")
    access_key = models.CharField(max_length=44, blank=True, default="", verbose_name="Chave")
    protocol = models.CharField(max_length=64, blank=True, default="", verbose_name="Protocolo")
    rejection_code = models.CharField(max_length=16, blank=True, default="", verbose_name="cStat")
    rejection_message = models.CharField(
        max_length=512, blank=True, default="", verbose_name="Motivo rejeição"
    )
    number_consumed = models.BooleanField(default=False, verbose_name="Número consumido")
    correlation_id = models.UUIDField(default=uuid.uuid4, verbose_name="Correlação")
    payload_hash = models.CharField(max_length=64, blank=True, default="", verbose_name="Hash")
    last_validation = models.JSONField(null=True, blank=True, verbose_name="Última validação")

    class Meta:
        verbose_name = "NF-e"
        verbose_name_plural = "NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_nfe_invoice_tenant_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"]),
            models.Index(fields=["tenant", "access_key"]),
        ]

    def __str__(self) -> str:
        num = self.number or "—"
        return f"NF-e {self.series}/{num} — {self.status}"


class NfeInvoiceItem(UUIDPrimaryKeyModel):
    invoice = models.ForeignKey(
        NfeInvoice,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="NF-e",
    )
    line_number = models.PositiveIntegerField(verbose_name="Item")
    product = models.ForeignKey(
        NfeProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Produto",
    )
    code = models.CharField(max_length=60, verbose_name="Código")
    description = models.CharField(max_length=120, verbose_name="Descrição")
    ncm = models.CharField(max_length=8, verbose_name="NCM")
    cfop = models.CharField(max_length=4, verbose_name="CFOP")
    unit = models.CharField(max_length=6, default="UN", verbose_name="Unidade")
    quantity = models.DecimalField(max_digits=15, decimal_places=4, verbose_name="Quantidade")
    unit_price_cents = models.BigIntegerField(verbose_name="V. unitário (centavos)")
    discount_cents = models.BigIntegerField(default=0, verbose_name="Desconto (centavos)")
    total_cents = models.BigIntegerField(verbose_name="Total item (centavos)")
    origin = models.CharField(max_length=1, default="0", verbose_name="Origem")
    csosn = models.CharField(max_length=3, blank=True, default="", verbose_name="CSOSN")
    icms_cst = models.CharField(max_length=3, blank=True, default="", verbose_name="CST ICMS")
    taxes = models.JSONField(default=dict, blank=True, verbose_name="Impostos item")

    class Meta:
        verbose_name = "Item NF-e"
        verbose_name_plural = "Itens NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "line_number"],
                name="uq_nfe_item_invoice_line",
            ),
        ]
        ordering = ("line_number",)


class NfeInvoiceEvent(UUIDPrimaryKeyModel):
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.PROTECT,
        related_name="nfe_invoice_events",
    )
    invoice = models.ForeignKey(
        NfeInvoice,
        on_delete=models.CASCADE,
        related_name="events",
    )
    from_status = models.CharField(max_length=32, blank=True, default="")
    to_status = models.CharField(max_length=32)
    actor = models.CharField(max_length=64, default="system")
    metadata = models.JSONField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento NF-e"
        verbose_name_plural = "Eventos NF-e"
        ordering = ("occurred_at",)
        indexes = [models.Index(fields=["invoice", "occurred_at"])]


class NfeArtifact(TenantOwnedModel):
    """Artefatos fiscais da NF-e (I1: XML; I2: DANFE). Separado de NfArtifact (NFS-e)."""

    class Kind(models.TextChoices):
        XML_AUTHORIZED = "xml_authorized", "XML autorizado"
        XML_CANCEL = "xml_cancel", "XML cancelamento"
        XML_CCE = "xml_cce", "XML CCe (última)"
        DANFE_PDF = "danfe_pdf", "DANFE PDF"

    invoice = models.ForeignKey(
        NfeInvoice,
        on_delete=models.CASCADE,
        related_name="artifacts",
        verbose_name="NF-e",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices, verbose_name="Tipo")
    stored_file = models.ForeignKey(
        "ops.StoredFile",
        on_delete=models.PROTECT,
        related_name="nfe_artifacts",
        verbose_name="Arquivo",
    )
    checksum_sha256 = models.CharField(max_length=64, verbose_name="Checksum SHA-256")

    class Meta:
        verbose_name = "Artefato NF-e"
        verbose_name_plural = "Artefatos NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "kind"],
                name="uq_nfe_artifact_invoice_kind",
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} · {self.invoice_id}"

