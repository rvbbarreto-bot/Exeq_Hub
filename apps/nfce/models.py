"""Domínio NFC-e modelo 65 — greenfield PDV."""

from __future__ import annotations

import uuid

from django.db import models

from shared.models import UUIDPrimaryKeyModel
from shared.tenancy import TenantOwnedModel


class NfceNumberSeries(TenantOwnedModel):
    """Série mod 65 + próximo número por emitente e ambiente."""

    class Environment(models.TextChoices):
        HOMOLOG = "2", "Homologação"
        PRODUCTION = "1", "Produção"

    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="nfce_number_series",
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
        verbose_name = "Série NFC-e"
        verbose_name_plural = "Séries NFC-e"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "series", "tp_amb"],
                name="uq_nfce_series_provider_serie_amb",
            ),
        ]


class NfceInvoice(TenantOwnedModel):
    """Cupom fiscal NFC-e: draft → authorized (FSM)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        SUBMITTING = "submitting", "Enviando"
        POLLING = "polling", "Consultando"
        AUTHORIZED = "authorized", "Autorizada"
        REJECTED = "rejected", "Rejeitada"
        FAILED = "failed", "Falhou"
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
        related_name="nfce_invoices",
        verbose_name="Emitente",
    )
    nature_operation = models.CharField(
        max_length=60, default="VENDA", verbose_name="Natureza da operação"
    )
    series = models.PositiveIntegerField(default=1, verbose_name="Série")
    number = models.PositiveIntegerField(null=True, blank=True, verbose_name="Número")
    tp_amb = models.CharField(max_length=1, default="2", verbose_name="Ambiente")
    issue_date = models.DateField(verbose_name="Data de emissão")
    payment_method = models.CharField(max_length=2, default="99", verbose_name="Forma pag. tPag")
    payment_amount_cents = models.BigIntegerField(null=True, blank=True, verbose_name="Valor pag.")
    discount_cents = models.BigIntegerField(default=0, verbose_name="Desconto (centavos)")
    total_cents = models.BigIntegerField(default=0, verbose_name="Total (centavos)")
    identification_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Identificação consumidor (transitória)",
    )
    omit_dest = models.BooleanField(default=True, verbose_name="Omitir dest no XML")
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
        verbose_name = "NFC-e"
        verbose_name_plural = "NFC-e"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_nfce_invoice_tenant_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"]),
            models.Index(fields=["tenant", "access_key"]),
        ]


class NfceInvoiceItem(UUIDPrimaryKeyModel):
    invoice = models.ForeignKey(
        NfceInvoice,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="NFC-e",
    )
    line_number = models.PositiveIntegerField(verbose_name="Item")
    product = models.ForeignKey(
        "nfe.NfeProduct",
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
        verbose_name = "Item NFC-e"
        verbose_name_plural = "Itens NFC-e"
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "line_number"],
                name="uq_nfce_item_invoice_line",
            ),
        ]
        ordering = ("line_number",)


class NfceInvoiceEvent(UUIDPrimaryKeyModel):
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.PROTECT,
        related_name="nfce_invoice_events",
    )
    invoice = models.ForeignKey(
        NfceInvoice,
        on_delete=models.CASCADE,
        related_name="events",
    )
    from_status = models.CharField(max_length=32, blank=True, default="")
    to_status = models.CharField(max_length=32)
    actor = models.CharField(max_length=64, default="system")
    metadata = models.JSONField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento NFC-e"
        verbose_name_plural = "Eventos NFC-e"
        ordering = ("occurred_at",)
        indexes = [models.Index(fields=["invoice", "occurred_at"])]


class TenantCscToken(TenantOwnedModel):
    """CSC homolog/prod por emitente (QR Code NFC-e)."""

    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="nfce_csc_tokens",
        verbose_name="Emitente",
    )
    tp_amb = models.CharField(max_length=1, default="2", verbose_name="Ambiente")
    csc_id = models.CharField(max_length=6, verbose_name="Id CSC")
    csc_token = models.CharField(max_length=64, verbose_name="Token CSC")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "CSC NFC-e"
        verbose_name_plural = "CSC NFC-e"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "tp_amb", "csc_id"],
                name="uq_nfce_csc_tenant_provider_amb_id",
            ),
        ]


class NfceArtifact(TenantOwnedModel):
    """Artefatos NFC-e (XML autorizado + DANFE cupom PDF)."""

    class Kind(models.TextChoices):
        XML_AUTHORIZED = "xml_authorized", "XML autorizado"
        DANFE_PDF = "danfe_pdf", "DANFE NFC-e PDF"

    invoice = models.ForeignKey(
        NfceInvoice,
        on_delete=models.CASCADE,
        related_name="artifacts",
        verbose_name="NFC-e",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices, verbose_name="Tipo")
    stored_file = models.ForeignKey(
        "ops.StoredFile",
        on_delete=models.PROTECT,
        related_name="nfce_artifacts",
        verbose_name="Arquivo",
    )
    checksum_sha256 = models.CharField(max_length=64, verbose_name="Checksum SHA-256")

    class Meta:
        verbose_name = "Artefato NFC-e"
        verbose_name_plural = "Artefatos NFC-e"
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "kind"],
                name="uq_nfce_artifact_invoice_kind",
            ),
        ]
