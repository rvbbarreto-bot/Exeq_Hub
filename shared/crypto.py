import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CryptoError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY or ""
    if not key:
        raise CryptoError("FIELD_ENCRYPTION_KEY não configurada")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except InvalidToken as exc:
        raise CryptoError("Falha ao descriptografar") from exc


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
