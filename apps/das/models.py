from decimal import Decimal

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F

from shared.tenancy import TenantOwnedModel

competencia_validator = RegexValidator(r"^\d{4}-\d{2}$", "Use AAAA-MM")


class GuiaFiscal(TenantOwnedModel):
    class TipoGuia(models.TextChoices):
        DAS = "DAS", "DAS"
        DARF = "DARF", "DARF"

    class Status(models.TextChoices):
        PROCESSANDO = "PROCESSANDO", "Processando"
        DISPONIVEL = "DISPONIVEL", "Disponível"
        PAGO = "PAGO", "Pago"
        CANCELADO = "CANCELADO", "Cancelado"
        RETIFICADO = "RETIFICADO", "Retificado"
        VENCIDO = "VENCIDO", "Vencido"
        EM_CONTESTACAO = "EM_CONTESTACAO", "Em contestação"

    class ComplianceStatus(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        APROVADO = "aprovado", "Aprovado"
        BLOQUEADO = "bloqueado", "Bloqueado"
        DISPENSADO = "dispensado", "Dispensado"

    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.PROTECT,
        related_name="guias_fiscais",
        verbose_name="Prestador",
    )
    tipo_guia = models.CharField(
        max_length=8, choices=TipoGuia.choices, verbose_name="Tipo de guia"
    )
    competencia = models.CharField(
        max_length=7,
        validators=[competencia_validator],
        verbose_name="Competência",
    )
    data_vencimento = models.DateField(
        null=True, blank=True, verbose_name="Data de vencimento"
    )
    valor_principal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Valor principal",
    )
    valor_multa = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Valor multa",
    )
    valor_juros = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Valor juros",
    )
    valor_total = models.GeneratedField(
        expression=F("valor_principal") + F("valor_multa") + F("valor_juros"),
        output_field=models.DecimalField(max_digits=14, decimal_places=2),
        db_persist=True,
        verbose_name="Valor total",
    )
    linha_digitavel = models.TextField(
        blank=True, default="", verbose_name="Linha digitável"
    )
    pix_copia_cola = models.TextField(
        blank=True, default="", verbose_name="PIX copia e cola"
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PROCESSANDO,
        verbose_name="Status",
    )
    compliance_status = models.CharField(
        max_length=16,
        choices=ComplianceStatus.choices,
        default=ComplianceStatus.PENDENTE,
        verbose_name="Status de compliance",
    )
    compliance_motivo = models.TextField(
        blank=True, default="", verbose_name="Motivo compliance"
    )
    pdf_storage_key = models.TextField(
        blank=True, default="", verbose_name="Chave storage PDF"
    )
    pdf_file = models.ForeignKey(
        "ops.StoredFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guias_fiscais",
        verbose_name="Arquivo PDF",
    )
    versao_atual = models.PositiveIntegerField(default=1, verbose_name="Versão")
    idempotency_key = models.CharField(
        max_length=128, verbose_name="Chave de idempotência"
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadados")

    class Meta:
        verbose_name = "Guia fiscal"
        verbose_name_plural = "Guias fiscais"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_guia_fiscal_tenant_idempotency",
            ),
            models.UniqueConstraint(
                fields=["tenant", "provider", "tipo_guia", "competencia", "versao_atual"],
                name="uq_guia_fiscal_natural_key",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_principal__gte=0)
                & models.Q(valor_multa__gte=0)
                & models.Q(valor_juros__gte=0),
                name="ck_guia_fiscal_valores_nao_negativos",
            ),
            models.CheckConstraint(
                condition=models.Q(versao_atual__gte=1),
                name="ck_guia_fiscal_versao_min",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "competencia", "status"]),
        ]
