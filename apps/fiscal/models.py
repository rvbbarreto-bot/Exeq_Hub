from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.master_data.models import TaxRegime
from shared.tenancy import TenantOwnedModel


def default_publish_checklist() -> dict:
    return {
        "csv_validated": False,
        "rules_reviewed": False,
        "terms_accepted": False,
    }


class FiscalProfile(TenantOwnedModel):
    name = models.CharField(max_length=128, verbose_name="Nome")
    tax_regime = models.CharField(
        max_length=32, choices=TaxRegime.choices, verbose_name="Regime tributário"
    )
    iss_retention_policy = models.CharField(
        max_length=32, default="by_rule", verbose_name="Política retenção ISS"
    )
    status = models.CharField(max_length=16, default="active", verbose_name="Status")

    class Meta:
        verbose_name = "Perfil fiscal"
        verbose_name_plural = "Perfis fiscais"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"],
                name="uq_fiscal_profile_tenant_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.tenant.slug}]"


class TaxRuleCatalog(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PUBLISHED = "published", "Publicado"
        SUPERSEDED = "superseded", "Substituído"

    version = models.PositiveIntegerField(verbose_name="Versão")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Status",
    )
    publish_checklist = models.JSONField(
        default=default_publish_checklist, verbose_name="Checklist de publicação"
    )
    published_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Publicado em"
    )

    class Meta:
        verbose_name = "Catálogo de regras"
        verbose_name_plural = "Catálogos de regras"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "version"],
                name="uq_tax_catalog_tenant_version",
            ),
            models.UniqueConstraint(
                fields=["tenant"],
                condition=Q(status="published"),
                name="uq_tax_catalog_one_published",
            ),
        ]

    def __str__(self) -> str:
        return f"v{self.version}:{self.status}"


class MunicipalTaxRule(TenantOwnedModel):
    catalog = models.ForeignKey(
        TaxRuleCatalog,
        on_delete=models.CASCADE,
        related_name="rules",
        verbose_name="Catálogo",
    )
    fiscal_profile = models.ForeignKey(
        FiscalProfile,
        on_delete=models.PROTECT,
        related_name="tax_rules",
        verbose_name="Perfil fiscal",
    )
    ibge_code = models.CharField(max_length=7, verbose_name="Código IBGE")
    municipio_nome = models.CharField(max_length=128, verbose_name="Município")
    uf = models.CharField(max_length=2, verbose_name="UF")
    service_code = models.CharField(max_length=32, verbose_name="Código do serviço")
    tax_regime = models.CharField(
        max_length=32, choices=TaxRegime.choices, verbose_name="Regime tributário"
    )
    iss_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name="Alíquota ISS"
    )
    irrf_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name="Alíquota IRRF"
    )
    pis_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0"), verbose_name="Alíquota PIS"
    )
    cofins_rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Alíquota COFINS",
    )
    iss_retained = models.BooleanField(default=False, verbose_name="ISS retido")
    simples_codigo_tributacao = models.SmallIntegerField(
        null=True, blank=True, verbose_name="Código tributação SN"
    )
    c_trib_mun = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name="Código tributação municipal (cTribMun)",
    )
    valid_from = models.DateField(verbose_name="Válido de")
    valid_to = models.DateField(null=True, blank=True, verbose_name="Válido até")
    priority = models.IntegerField(default=100, verbose_name="Prioridade")
    focus_field_overrides = models.JSONField(
        default=dict, blank=True, verbose_name="Overrides Focus"
    )

    class Meta:
        verbose_name = "Regra municipal"
        verbose_name_plural = "Regras municipais"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "tenant",
                    "catalog",
                    "fiscal_profile",
                    "ibge_code",
                    "service_code",
                    "tax_regime",
                    "valid_from",
                ],
                name="uq_municipal_tax_rule_natural_key",
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant", "ibge_code", "service_code", "tax_regime", "priority"],
                name="idx_tax_rule_resolve",
            )
        ]

    def __str__(self) -> str:
        return f"{self.ibge_code}:{self.service_code}"


class RtcNormativeVersion(models.Model):
    """Pilar 3 — pacote normativo RTC (NT / LC) versionado globalmente."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PUBLISHED = "published", "Publicado"
        SUPERSEDED = "superseded", "Substituído"

    version_label = models.CharField(max_length=64, unique=True, verbose_name="Rótulo")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, verbose_name="Status"
    )
    nt_refs = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Referências NT",
        help_text="Ex.: SE/CGNFS-e NT 009; LC 214/2025; ADCT art. 125",
    )
    changelog = models.TextField(blank=True, default="", verbose_name="Changelog")
    owner = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Responsável conformidade"
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="Publicado em")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Versão normativa RTC"
        verbose_name_plural = "Versões normativas RTC"
        ordering = ["-published_at", "-created_at"]

    def __str__(self) -> str:
        return f"{self.version_label} ({self.status})"


class RtcClassificationCode(models.Model):
    """Pilar 2 — CST / cClassTrib / cIndOp oficiais por versão normativa."""

    class Kind(models.TextChoices):
        CST = "cst", "CST IBS/CBS"
        C_CLASS_TRIB = "c_class_trib", "cClassTrib"
        C_IND_OP = "c_ind_op", "cIndOp"

    version = models.ForeignKey(
        RtcNormativeVersion,
        on_delete=models.CASCADE,
        related_name="codes",
        verbose_name="Versão normativa",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, verbose_name="Tipo")
    code = models.CharField(max_length=16, verbose_name="Código")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="Descrição")
    requires_group = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="Grupo XML exigido",
        help_text="Ex.: gIBSCBS, gIBSCBSMono, vazio se não aplicável",
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Código classificação RTC"
        verbose_name_plural = "Códigos classificação RTC"
        ordering = ["kind", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "kind", "code"],
                name="uq_rtc_classification_version_kind_code",
            )
        ]
        indexes = [
            models.Index(fields=["kind", "code"], name="idx_rtc_class_kind_code"),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.code}"
