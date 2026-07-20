from django.db import models

from shared.tenancy import TenantOwnedModel


class TaxRegime(models.TextChoices):
    SIMPLES = "simples_nacional", "Simples Nacional"
    PRESUMIDO = "lucro_presumido", "Lucro Presumido"
    REAL = "lucro_real", "Lucro Real"


class Provider(TenantOwnedModel):
    document = models.CharField(max_length=14, verbose_name="CNPJ")
    legal_name = models.CharField(max_length=255, verbose_name="Razão social")
    trade_name = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Nome fantasia"
    )
    municipal_registration = models.CharField(
        max_length=32, blank=True, default="", verbose_name="Inscrição municipal"
    )
    tax_regime = models.CharField(
        max_length=32, choices=TaxRegime.choices, verbose_name="Regime tributário"
    )
    address = models.JSONField(default=dict, blank=True, verbose_name="Endereço")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Prestador"
        verbose_name_plural = "Prestadores"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "document"],
                name="uq_provider_tenant_document",
            )
        ]

    def __str__(self) -> str:
        return self.legal_name


class Customer(TenantOwnedModel):
    class DocumentType(models.TextChoices):
        CPF = "cpf", "CPF"
        CNPJ = "cnpj", "CNPJ"

    document = models.CharField(max_length=14, verbose_name="Documento")
    document_type = models.CharField(
        max_length=4, choices=DocumentType.choices, verbose_name="Tipo de documento"
    )
    name = models.CharField(max_length=255, verbose_name="Nome")
    email = models.EmailField(blank=True, default="", verbose_name="E-mail")
    address = models.JSONField(default=dict, blank=True, verbose_name="Endereço")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Tomador"
        verbose_name_plural = "Tomadores"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "document"],
                name="uq_customer_tenant_document",
            )
        ]

    def __str__(self) -> str:
        return self.name


class ServiceCatalogItem(TenantOwnedModel):
    service_code = models.CharField(max_length=32, verbose_name="Código do serviço")
    description = models.TextField(verbose_name="Descrição")
    lc116_item = models.CharField(
        max_length=16, blank=True, default="", verbose_name="Item LC 116"
    )
    codigo_tributacao_nacional_iss = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name="Código tributação nacional ISS",
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Serviço do catálogo"
        verbose_name_plural = "Serviços do catálogo"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "service_code"],
                name="uq_service_tenant_code",
            )
        ]

    def __str__(self) -> str:
        return self.service_code
