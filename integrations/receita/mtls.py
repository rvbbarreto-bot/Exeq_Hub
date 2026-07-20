"""mTLS a partir de PFX (A1) para httpx/ssl."""

from __future__ import annotations

import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)

from integrations.receita.exceptions import ReceitaAuthError


@dataclass(frozen=True)
class MtlsMaterial:
    ssl_context: ssl.SSLContext
    _tmpdir: tempfile.TemporaryDirectory

    def close(self) -> None:
        self._tmpdir.cleanup()


def build_mtls_context(*, pfx_bytes: bytes, password: str = "") -> MtlsMaterial:
    pwd = password.encode() if password else None
    try:
        key, cert, _chain = pkcs12.load_key_and_certificates(pfx_bytes, pwd)
    except Exception as exc:  # noqa: BLE001
        raise ReceitaAuthError("Falha ao ler PFX para mTLS SERPRO") from exc
    if key is None or cert is None:
        raise ReceitaAuthError("PFX sem chave/certificado privado")

    tmp = tempfile.TemporaryDirectory(prefix="exeq_serpro_mtls_")
    root = Path(tmp.name)
    cert_path = root / "cert.pem"
    key_path = root / "key.pem"
    cert_path.write_bytes(cert.public_bytes(Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )

    ctx = ssl.create_default_context()
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return MtlsMaterial(ssl_context=ctx, _tmpdir=tmp)
