import hashlib

from django.db import models

from shared.tenancy import TenantOwnedModel


class OutboxMessage(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PROCESSING = "processing", "Processando"
        PROCESSED = "processed", "Processado"
        FAILED = "failed", "Falhou"
        DEAD = "dead", "Morta"

    event_type = models.CharField(max_length=128, verbose_name="Tipo de evento")
    aggregate_type = models.CharField(max_length=64, verbose_name="Tipo do agregado")
    aggregate_id = models.UUIDField(verbose_name="ID do agregado")
    payload = models.JSONField(default=dict, verbose_name="Payload")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    attempts = models.PositiveIntegerField(default=0, verbose_name="Tentativas")
    available_at = models.DateTimeField(verbose_name="Disponível em")
    processed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Processado em"
    )
    last_error = models.TextField(blank=True, default="", verbose_name="Último erro")
    correlation_id = models.UUIDField(
        null=True, blank=True, verbose_name="ID de correlação"
    )

    class Meta:
        verbose_name = "Mensagem outbox"
        verbose_name_plural = "Mensagens outbox"
        indexes = [
            models.Index(fields=["status", "available_at"]),
            models.Index(fields=["tenant", "event_type", "created_at"]),
        ]


class StoredFile(TenantOwnedModel):
    class Backend(models.TextChoices):
        LOCAL = "local", "Local"
        S3 = "s3", "S3"
        MINIO = "minio", "MinIO"

    backend = models.CharField(
        max_length=16,
        choices=Backend.choices,
        default=Backend.LOCAL,
        verbose_name="Backend",
    )
    bucket = models.CharField(max_length=128, blank=True, default="", verbose_name="Bucket")
    object_key = models.TextField(verbose_name="Chave do objeto")
    content_type = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Content-Type"
    )
    size_bytes = models.BigIntegerField(default=0, verbose_name="Tamanho (bytes)")
    checksum_sha256 = models.CharField(max_length=64, verbose_name="Checksum SHA-256")
    encryption = models.CharField(
        max_length=32, default="envelope", verbose_name="Criptografia"
    )
    purpose = models.CharField(max_length=64, verbose_name="Finalidade")

    class Meta:
        verbose_name = "Arquivo armazenado"
        verbose_name_plural = "Arquivos armazenados"
        indexes = [models.Index(fields=["tenant", "purpose"])]
        constraints = [
            models.UniqueConstraint(
                fields=["backend", "bucket", "object_key"],
                name="uq_stored_file_backend_bucket_key",
            )
        ]

    @staticmethod
    def checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
