from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12


class PfxParseError(ValueError):
    pass


@dataclass(frozen=True)
class PfxInfo:
    not_before: datetime
    not_after: datetime
    subject: str


def parse_pfx(pfx_bytes: bytes, password: str = "") -> PfxInfo:
    try:
        key, cert, _additional = pkcs12.load_key_and_certificates(
            pfx_bytes,
            password.encode() if password is not None else None,
        )
    except Exception as exc:
        raise PfxParseError("PFX inválido ou senha incorreta") from exc

    if cert is None:
        raise PfxParseError("PFX sem certificado")

    not_before = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else cert.not_valid_before.replace(tzinfo=timezone.utc)
    not_after = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=timezone.utc)
    subject = cert.subject.rfc4514_string()
    return PfxInfo(not_before=not_before, not_after=not_after, subject=subject)
