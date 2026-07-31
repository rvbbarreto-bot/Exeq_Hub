"""mTLS a partir de PFX A1 (ICP-Brasil) para cliente SEFIN/ADN."""

from __future__ import annotations

import os
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


class SefinMtlsError(RuntimeError):
    """Falha ao montar contexto mTLS a partir do PFX."""


@dataclass
class SefinMtlsMaterial:
    ssl_context: ssl.SSLContext

    def close(self) -> None:
        """No-op compatível: PEM já removidos após load (SEC-P2-06)."""
        return None


def build_sefin_mtls_context(*, pfx_bytes: bytes, password: str = "") -> SefinMtlsMaterial:
    pwd = password.encode() if password else None
    try:
        key, cert, _chain = pkcs12.load_key_and_certificates(pfx_bytes, pwd)
    except Exception as exc:  # noqa: BLE001
        raise SefinMtlsError("Falha ao ler PFX para mTLS SEFIN") from exc
    if key is None or cert is None:
        raise SefinMtlsError("PFX sem chave/certificado privado")

    # SEC-P2-06: gravar PEM só o necessário para load_cert_chain e apagar em seguida.
    # O SSLContext mantém o material em memória; não deixar key.pem no disco até close().
    tmp = tempfile.TemporaryDirectory(prefix="exeq_sefin_mtls_")
    try:
        root = Path(tmp.name)
        cert_path = root / "cert.pem"
        key_path = root / "key.pem"
        cert_path.write_bytes(cert.public_bytes(Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        )
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        ctx = ssl.create_default_context()
        ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    finally:
        tmp.cleanup()

    return SefinMtlsMaterial(ssl_context=ctx)
