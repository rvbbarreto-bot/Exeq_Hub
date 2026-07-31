"""mTLS a partir de PEM (.crt + .key) para a API do Banco Inter."""

from __future__ import annotations

import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path

from integrations.payments.errors import PaymentGatewayError


@dataclass
class InterMtlsMaterial:
    ssl_context: ssl.SSLContext
    _tmpdir: tempfile.TemporaryDirectory | None = None

    def close(self) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None


def build_inter_mtls_context(
    *,
    cert_pem: str | None = None,
    key_pem: str | None = None,
    cert_path: str | None = None,
    key_path: str | None = None,
) -> InterMtlsMaterial:
    """
    Monta SSLContext com certificado de cliente.
    Aceita conteúdo PEM ou caminhos de arquivo (.crt / .key).
    """
    tmp: tempfile.TemporaryDirectory | None = None
    c_path = (cert_path or "").strip()
    k_path = (key_path or "").strip()

    if cert_pem and key_pem:
        tmp = tempfile.TemporaryDirectory(prefix="exeq_inter_mtls_")
        root = Path(tmp.name)
        c_file = root / "cert.pem"
        k_file = root / "key.pem"
        c_file.write_text(cert_pem.strip() + "\n", encoding="utf-8")
        k_file.write_text(key_pem.strip() + "\n", encoding="utf-8")
        c_path, k_path = str(c_file), str(k_file)
    elif not (c_path and k_path):
        raise PaymentGatewayError(
            "Certificado Inter ausente (cert_pem/key_pem ou INTER_CERT_PATH/INTER_KEY_PATH)"
        )

    if not Path(c_path).is_file() or not Path(k_path).is_file():
        if tmp is not None:
            tmp.cleanup()
        raise PaymentGatewayError("Arquivos de certificado/chave Inter inválidos")

    try:
        ctx = ssl.create_default_context()
        ctx.load_cert_chain(certfile=c_path, keyfile=k_path)
    except Exception as exc:  # noqa: BLE001
        if tmp is not None:
            tmp.cleanup()
        raise PaymentGatewayError(f"Falha ao carregar mTLS Inter: {exc}") from exc

    return InterMtlsMaterial(ssl_context=ctx, _tmpdir=tmp)
