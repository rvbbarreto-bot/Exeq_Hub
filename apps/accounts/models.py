from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from shared.models import TimeStampedModel, UUIDPrimaryKeyModel


class Tenant(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ativo"
        SUSPENDED = "suspended", "Suspenso"
        PROVISIONING = "provisioning", "Provisionando"

    slug = models.SlugField(max_length=64, unique=True, verbose_name="Slug")
    legal_name = models.CharField(max_length=255, verbose_name="Razão social")
    document = models.CharField(max_length=14, unique=True, verbose_name="CNPJ")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Status",
    )
    focus_layout = models.CharField(
        max_length=16, default="nfsen", verbose_name="Layout Focus"
    )
    settings = models.JSONField(default=dict, blank=True, verbose_name="Configurações")

    class Meta:
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return self.slug


class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str | None = None, **extra):
        if not email:
            raise ValueError("email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_platform_admin", True)
        extra.setdefault("is_active", True)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, UUIDPrimaryKeyModel):
    email = models.EmailField(unique=True, verbose_name="E-mail")
    name = models.CharField(max_length=255, verbose_name="Nome")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    is_staff = models.BooleanField(default=False, verbose_name="Equipe")
    is_platform_admin = models.BooleanField(
        default=False, verbose_name="Admin da plataforma"
    )
    last_login_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Último acesso"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    def __str__(self) -> str:
        return self.email


class TenantRole(UUIDPrimaryKeyModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    is_system = models.BooleanField(default=True)
    permissions = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "Papel do tenant"
        verbose_name_plural = "Papéis do tenant"

    def __str__(self) -> str:
        return self.code


class TenantMembership(TimeStampedModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.ForeignKey(
        TenantRole,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Vínculo no tenant"
        verbose_name_plural = "Vínculos no tenant"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"],
                name="uq_tenant_membership_tenant_user",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.tenant_id}"


class TenantSecret(TimeStampedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="secrets")
    provider = models.CharField(max_length=64)
    key_name = models.CharField(max_length=64)
    ciphertext = models.TextField()
    key_version = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Segredo do tenant"
        verbose_name_plural = "Segredos do tenant"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "key_name"],
                name="uq_tenant_secret_provider_key",
            )
        ]


class DigitalCertificate(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ativo"
        EXPIRING = "expiring", "A expirar"
        EXPIRED = "expired", "Expirado"
        REVOKED = "revoked", "Revogado"

    class CertType(models.TextChoices):
        A1 = "a1", "A1"
        A3 = "a3", "A3"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="certificates",
        verbose_name="Tenant",
    )
    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certificates",
        verbose_name="Prestador",
    )
    label = models.CharField(max_length=128, verbose_name="Rótulo")
    cnpj = models.CharField(max_length=14, verbose_name="CNPJ")
    cert_type = models.CharField(
        max_length=8,
        choices=CertType.choices,
        default=CertType.A1,
        verbose_name="Tipo",
    )
    is_primary = models.BooleanField(default=False, verbose_name="Principal")
    version = models.PositiveIntegerField(default=1, verbose_name="Versão")
    key_usage = models.JSONField(default=list, blank=True, verbose_name="Usos da chave")
    not_before = models.DateTimeField(verbose_name="Válido de")
    not_after = models.DateTimeField(verbose_name="Válido até")
    thumbprint_sha256 = models.CharField(max_length=64, verbose_name="Thumbprint SHA-256")
    stored_file = models.ForeignKey(
        "ops.StoredFile",
        on_delete=models.PROTECT,
        related_name="certificates",
        verbose_name="Arquivo",
    )
    password_secret = models.ForeignKey(
        "accounts.TenantSecret",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Segredo da senha",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Certificado digital"
        verbose_name_plural = "Certificados digitais"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "thumbprint_sha256"],
                name="uq_certificate_tenant_thumbprint",
            ),
            models.UniqueConstraint(
                fields=["tenant", "cnpj"],
                condition=models.Q(is_primary=True),
                name="uq_certificate_tenant_cnpj_primary",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "not_after"]),
            models.Index(fields=["tenant", "cnpj", "is_primary"]),
        ]


class CertificateAudit(UUIDPrimaryKeyModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="certificate_audits")
    certificate = models.ForeignKey(
        DigitalCertificate,
        on_delete=models.CASCADE,
        related_name="audits",
    )
    action = models.CharField(max_length=64)
    actor_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Auditoria de certificado"
        verbose_name_plural = "Auditorias de certificado"


class ElectronicProxy(TimeStampedModel):
    """Procuração eletrônica e-CAC (outorgante → outorgado) para SERPRO TERCEIROS."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        ACTIVE = "active", "Ativa"
        EXPIRING = "expiring", "A expirar"
        EXPIRED = "expired", "Expirada"
        REVOKED = "revoked", "Revogada"

    class DocumentType(models.TextChoices):
        CNPJ = "cnpj", "CNPJ"
        CPF = "cpf", "CPF"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="electronic_proxies",
        verbose_name="Tenant",
    )
    provider = models.ForeignKey(
        "master_data.Provider",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="electronic_proxies",
        verbose_name="Prestador",
    )
    principal_cnpj = models.CharField(
        max_length=14, verbose_name="CNPJ outorgante"
    )
    proxy_document = models.CharField(
        max_length=14, verbose_name="Documento outorgado"
    )
    proxy_document_type = models.CharField(
        max_length=4,
        choices=DocumentType.choices,
        default=DocumentType.CNPJ,
        verbose_name="Tipo documento outorgado",
    )
    ecac_service_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Serviços e-CAC",
        help_text='Ex.: ["PGDASD","GERARDAS12"]',
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    valid_from = models.DateField(verbose_name="Válida de")
    valid_to = models.DateField(null=True, blank=True, verbose_name="Válida até")
    label = models.CharField(max_length=128, blank=True, default="", verbose_name="Rótulo")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadados")

    class Meta:
        verbose_name = "Procuração eletrônica"
        verbose_name_plural = "Procurações eletrônicas"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "principal_cnpj", "proxy_document"],
                condition=models.Q(
                    status__in=["pending", "active", "expiring"]
                ),
                name="uq_electronic_proxy_active_pair",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "principal_cnpj", "status"]),
            models.Index(fields=["tenant", "valid_to"]),
        ]

    def __str__(self) -> str:
        return f"{self.principal_cnpj}→{self.proxy_document} ({self.status})"
