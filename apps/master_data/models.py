from django.db import models

from shared.tenancy import TenantOwnedModel


class TaxRegime(models.TextChoices):
    SIMPLES = "simples_nacional", "Simples Nacional"
    PRESUMIDO = "lucro_presumido", "Lucro Presumido"
    REAL = "lucro_real", "Lucro Real"


class DataSource(models.TextChoices):
    MANUAL = "manual", "Manual"
    RECEITA = "receita_federal", "Receita Federal"


class CadastralEnrichmentMixin(models.Model):
    """Campos cadastrais públicos (Receita) + contato operacional manual."""

    situacao_cadastral = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Situação cadastral"
    )
    data_abertura = models.DateField(
        null=True, blank=True, verbose_name="Data de abertura"
    )
    cnae_principal = models.CharField(
        max_length=255, blank=True, default="", verbose_name="CNAE principal"
    )
    cnaes_secundarios = models.JSONField(
        default=list,
        blank=True,
        verbose_name="CNAEs secundários",
    )
    natureza_juridica = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Natureza jurídica"
    )
    porte = models.CharField(max_length=64, blank=True, default="", verbose_name="Porte")
    whatsapp = models.CharField(
        max_length=32, blank=True, default="", verbose_name="WhatsApp"
    )
    contato_nome = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Nome do contato"
    )
    data_source = models.CharField(
        max_length=32,
        choices=DataSource.choices,
        default=DataSource.MANUAL,
        verbose_name="Origem dos dados",
    )
    receita_raw_payload = models.JSONField(
        null=True, blank=True, verbose_name="Payload bruto Receita"
    )
    last_lookup_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Última consulta cadastral"
    )

    class Meta:
        abstract = True


class Provider(CadastralEnrichmentMixin, TenantOwnedModel):
    document = models.CharField(max_length=14, verbose_name="CNPJ")
    legal_name = models.CharField(max_length=255, verbose_name="Razão social")
    trade_name = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Nome fantasia"
    )
    municipal_registration = models.CharField(
        max_length=32, blank=True, default="", verbose_name="Inscrição municipal"
    )
    state_registration = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="Inscrição estadual (IE)",
        help_text="Obrigatória para emissão real NF-e (SEFAZ); opcional em stub.",
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


class Customer(CadastralEnrichmentMixin, TenantOwnedModel):
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
    class OperationKind(models.TextChoices):
        SERVICO_ISS = "servico_iss", "Serviço tributável ISS"
        LOCACAO_BEM = "locacao_bem", "Locação de bem (sem NFS-e)"

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
    operation_kind = models.CharField(
        max_length=32,
        choices=OperationKind.choices,
        default=OperationKind.SERVICO_ISS,
        verbose_name="Tipo de operação",
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
        from apps.master_data.national_service_import import service_catalog_display_label

        return service_catalog_display_label(
            service_code=self.service_code,
            codigo_tributacao_nacional_iss=self.codigo_tributacao_nacional_iss,
            description=self.description,
        )


class NationalServiceCatalogVersion(models.Model):
    """Versão importada do Anexo B — Lista de Serviço Nacional (NFS-e)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PUBLISHED = "published", "Publicada"
        SUPERSEDED = "superseded", "Substituída"

    version_label = models.CharField(
        max_length=64, unique=True, verbose_name="Rótulo da versão"
    )
    source_filename = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Arquivo origem"
    )
    sheet_name = models.CharField(
        max_length=64, blank=True, default="LISTA.SERV.NAC.", verbose_name="Aba"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, verbose_name="Status"
    )
    row_count = models.PositiveIntegerField(default=0, verbose_name="Qtd. códigos")
    notes = models.TextField(blank=True, default="", verbose_name="Observações")
    imported_at = models.DateTimeField(auto_now_add=True, verbose_name="Importado em")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="Publicado em")

    class Meta:
        verbose_name = "Versão Lista Serviço Nacional"
        verbose_name_plural = "Versões Lista Serviço Nacional"
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        return f"{self.version_label} ({self.status})"


class NationalServiceItem(models.Model):
    """Folha da Lista de Serviço Nacional (código de tributação nacional ISS)."""

    version = models.ForeignKey(
        NationalServiceCatalogVersion,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Versão",
    )
    codigo = models.CharField(max_length=16, verbose_name="Código tributação nacional")
    item = models.PositiveSmallIntegerField(verbose_name="Item LC 116")
    subitem = models.PositiveSmallIntegerField(verbose_name="Subitem")
    desdobro = models.PositiveSmallIntegerField(default=0, verbose_name="Desdobro nacional")
    description = models.TextField(verbose_name="Descrição")
    lc116_hint = models.CharField(
        max_length=16, blank=True, default="", verbose_name="Sugestão LC 116"
    )

    class Meta:
        verbose_name = "Código Serviço Nacional"
        verbose_name_plural = "Códigos Serviço Nacional"
        ordering = ["codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "codigo"],
                name="uq_national_service_version_codigo",
            )
        ]
        indexes = [
            models.Index(fields=["codigo"], name="idx_national_service_codigo"),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.description[:60]}"
