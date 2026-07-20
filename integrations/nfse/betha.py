from typing import Any

from integrations.nfse.port import NfseEmitResult


class BethaNfseProvider:
    """Adaptador Betha — municipal alternativo."""

    kind = "betha"

    def emitir(self, *, payload: dict[str, Any]) -> NfseEmitResult:
        issue_id = str(payload.get("issue_id", "unknown"))
        ref = f"BETHA-{issue_id.replace('-', '')[:12].upper()}"
        return NfseEmitResult(
            external_ref=ref,
            status="authorized",
            raw={"provider": "betha", "mode": "stub", "payload_keys": list(payload.keys())},
        )

    def consultar(self, *, ref: str) -> NfseEmitResult:
        return NfseEmitResult(
            external_ref=ref,
            status="authorized",
            raw={"provider": "betha", "mode": "stub", "action": "consultar"},
        )

    def cancelar(
        self,
        *,
        ref: str,
        justificativa: str,
        codigo_cancelamento: int | None = None,
    ) -> NfseEmitResult:
        return NfseEmitResult(
            external_ref=ref,
            status="cancelled",
            raw={
                "provider": "betha",
                "mode": "stub",
                "action": "cancelar",
                "justificativa": justificativa,
                "codigo_cancelamento": codigo_cancelamento,
            },
        )
