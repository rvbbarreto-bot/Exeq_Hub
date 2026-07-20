from django.db import transaction

from apps.accounts.models import TenantSecret
from shared.crypto import decrypt_bytes, encrypt_bytes


@transaction.atomic
def set_tenant_secret(
    *,
    tenant,
    provider: str,
    key_name: str,
    plaintext: str,
    key_version: int = 1,
    metadata: dict | None = None,
) -> TenantSecret:
    ciphertext = encrypt_bytes(plaintext.encode()).decode()
    secret, _ = TenantSecret.objects.update_or_create(
        tenant=tenant,
        provider=provider,
        key_name=key_name,
        defaults={
            "ciphertext": ciphertext,
            "key_version": key_version,
            "metadata": metadata or {},
        },
    )
    return secret


def get_tenant_secret_plaintext(*, tenant, provider: str, key_name: str) -> str | None:
    try:
        secret = TenantSecret.objects.get(
            tenant=tenant,
            provider=provider,
            key_name=key_name,
        )
    except TenantSecret.DoesNotExist:
        return None
    return decrypt_bytes(secret.ciphertext.encode()).decode()
