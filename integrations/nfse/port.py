"""Porta NFS-e — Focus (default) / Betha."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class NfseEmitResult:
    external_ref: str
    status: str
    raw: dict[str, Any]


class NfseProvider(Protocol):
    kind: str

    def emitir(self, *, payload: dict[str, Any]) -> NfseEmitResult: ...

    def consultar(self, *, ref: str) -> NfseEmitResult: ...

    def cancelar(
        self,
        *,
        ref: str,
        justificativa: str,
        codigo_cancelamento: int | None = None,
    ) -> NfseEmitResult: ...
