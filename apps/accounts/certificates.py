from datetime import datetime, timezone

from django.db import transaction

from apps.accounts.exceptions import CertificateNotUsableError
from apps.accounts.models import CertificateAudit, DigitalCertificate
from apps.accounts.secrets import set_tenant_secret
from apps.ops.models import StoredFile
from apps.ops.services import enqueue_outbox
from shared.crypto import CryptoError, decrypt_bytes, encrypt_bytes, sha256_hex
from shared.pfx import PfxParseError, parse_pfx
from shared.storage import get_storage

USABLE_STATUSES = frozenset(
    {
        DigitalCertificate.Status.ACTIVE,
        DigitalCertificate.Status.EXPIRING,
    }
)


def _status_for_validity(*, not_after: datetime) -> str:
    now = datetime.now(timezone.utc)
    if not_after <= now:
        return DigitalCertificate.Status.EXPIRED
    if (not_after - now).days <= 30:
        return DigitalCertificate.Status.EXPIRING
    return DigitalCertificate.Status.ACTIVE


def refresh_certificate_status(cert: DigitalCertificate) -> DigitalCertificate:
    if cert.status == DigitalCertificate.Status.REVOKED:
        return cert
    new_status = _status_for_validity(not_after=cert.not_after)
    if new_status != cert.status:
        cert.status = new_status
        cert.save(update_fields=["status", "updated_at"])
    return cert


def get_primary_certificate(*, tenant, cnpj: str) -> DigitalCertificate | None:
    digits = "".join(ch for ch in cnpj if ch.isdigit())
    cert = (
        DigitalCertificate.objects.filter(
            tenant=tenant,
            cnpj=digits,
            is_primary=True,
        )
        .select_related("password_secret")
        .first()
    )
    if cert is None:
        return None
    return refresh_certificate_status(cert)


def assert_certificate_usable(
    *,
    tenant,
    cnpj: str,
    purpose: str = "das",
) -> DigitalCertificate:
    """Bloqueia DAS/SERPRO (e usos futuros) sem A1 primary válido."""
    cert = get_primary_certificate(tenant=tenant, cnpj=cnpj)
    if cert is None:
        raise CertificateNotUsableError(
            "Certificado digital A1 primary ausente para o CNPJ"
        )
    if cert.status == DigitalCertificate.Status.EXPIRED:
        raise CertificateNotUsableError("Certificado digital expirado")
    if cert.status == DigitalCertificate.Status.REVOKED:
        raise CertificateNotUsableError("Certificado digital revogado")
    if cert.status not in USABLE_STATUSES:
        raise CertificateNotUsableError(
            f"Certificado digital indisponível (status={cert.status})"
        )
    usages = cert.key_usage or []
    if usages and purpose not in usages:
        raise CertificateNotUsableError(
            f"Certificado sem permissão para uso '{purpose}'"
        )
    return cert


@transaction.atomic
def upload_a1_certificate(
    *,
    tenant,
    label: str,
    cnpj: str,
    pfx_bytes: bytes,
    password: str = "",
    provider=None,
    actor_user=None,
    key_usage: list[str] | None = None,
    make_primary: bool = True,
) -> DigitalCertificate:
    digits = "".join(ch for ch in cnpj if ch.isdigit())
    info = parse_pfx(pfx_bytes, password=password)
    thumbprint = sha256_hex(pfx_bytes)
    encrypted = encrypt_bytes(pfx_bytes)
    object_key = f"certificates/{tenant.id}/{thumbprint}.pfx.enc"
    storage = get_storage()
    storage.put(
        key=object_key,
        data=encrypted,
        content_type="application/x-pkcs12",
    )
    stored = StoredFile.objects.create(
        tenant=tenant,
        backend=StoredFile.Backend.LOCAL,
        object_key=object_key,
        content_type="application/x-pkcs12",
        size_bytes=len(encrypted),
        checksum_sha256=sha256_hex(encrypted),
        encryption="envelope",
        purpose="certificate",
    )

    if make_primary:
        DigitalCertificate.objects.filter(
            tenant=tenant,
            cnpj=digits,
            is_primary=True,
        ).update(is_primary=False)

    version = 1
    prev = (
        DigitalCertificate.objects.filter(tenant=tenant, cnpj=digits)
        .order_by("-version")
        .first()
    )
    if prev is not None:
        version = prev.version + 1

    usages = key_usage if key_usage is not None else ["das", "nfse"]
    cert = DigitalCertificate.objects.create(
        tenant=tenant,
        provider=provider,
        label=label,
        cnpj=digits,
        cert_type=DigitalCertificate.CertType.A1,
        is_primary=make_primary,
        version=version,
        key_usage=usages,
        not_before=info.not_before,
        not_after=info.not_after,
        thumbprint_sha256=thumbprint,
        stored_file=stored,
        status=_status_for_validity(not_after=info.not_after),
    )

    if password:
        secret = set_tenant_secret(
            tenant=tenant,
            provider="certificate",
            key_name=f"pfx_password:{cert.id}",
            plaintext=password,
        )
        cert.password_secret = secret
        cert.save(update_fields=["password_secret", "updated_at"])

    CertificateAudit.objects.create(
        tenant=tenant,
        certificate=cert,
        action="uploaded" if version == 1 else "rotated",
        actor_user=actor_user,
        metadata={"label": label, "subject": info.subject, "version": version},
    )
    return cert


@transaction.atomic
def scan_expiring_certificates(*, alert_days: int = 30) -> int:
    """Atualiza status e emite outbox certificate.expiring. Retorna qtde alertada."""
    now = datetime.now(timezone.utc)
    alerted = 0
    qs = DigitalCertificate.objects.exclude(
        status=DigitalCertificate.Status.REVOKED,
    ).select_related("tenant")
    for cert in qs.iterator():
        before = cert.status
        refresh_certificate_status(cert)
        cert.refresh_from_db()
        days_left = (cert.not_after - now).days
        if cert.status in {
            DigitalCertificate.Status.EXPIRING,
            DigitalCertificate.Status.EXPIRED,
        } and (before != cert.status or days_left <= alert_days):
            enqueue_outbox(
                tenant=cert.tenant,
                event_type="certificate.expiring"
                if cert.status == DigitalCertificate.Status.EXPIRING
                else "certificate.expired",
                aggregate_type="digital_certificate",
                aggregate_id=cert.id,
                payload={
                    "certificate_id": str(cert.id),
                    "cnpj": cert.cnpj,
                    "status": cert.status,
                    "not_after": cert.not_after.isoformat(),
                    "days_left": days_left,
                },
            )
            CertificateAudit.objects.create(
                tenant=cert.tenant,
                certificate=cert,
                action="alert_sent",
                metadata={"status": cert.status, "days_left": days_left},
            )
            alerted += 1
    return alerted


def load_primary_pfx_material(*, tenant, cnpj: str) -> tuple[bytes, str]:
    """
    Retorna (pfx_bytes, password) do certificado A1 primary.
    PFX é armazenado criptografado em StoredFile; senha em TenantSecret.
    """
    cert = assert_certificate_usable(tenant=tenant, cnpj=cnpj, purpose="das")
    if cert.stored_file_id is None:
        raise CertificateNotUsableError("Certificado sem arquivo PFX armazenado")
    encrypted = get_storage().get(key=cert.stored_file.object_key)
    try:
        pfx_bytes = decrypt_bytes(encrypted)
    except CryptoError as exc:
        raise CertificateNotUsableError("Falha ao descriptografar PFX") from exc
    password = ""
    if cert.password_secret_id:
        from apps.accounts.secrets import get_tenant_secret_plaintext

        password = (
            get_tenant_secret_plaintext(
                tenant=tenant,
                provider="certificate",
                key_name=f"pfx_password:{cert.id}",
            )
            or ""
        )
    return pfx_bytes, password


__all__ = [
    "PfxParseError",
    "assert_certificate_usable",
    "get_primary_certificate",
    "load_primary_pfx_material",
    "refresh_certificate_status",
    "scan_expiring_certificates",
    "upload_a1_certificate",
]
