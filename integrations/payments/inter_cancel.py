"""Motivos de cancelamento Inter Cobrança v3 (campo obrigatório motivoCancelamento)."""

from __future__ import annotations

# Documentação / SDKs oficiais e legado v2 usados em produção Inter.
INTER_CANCEL_MOTIVOS = frozenset(
    {
        "ACERTOS",
        "APEDIDODOCLIENTE",
        "CLIENTE_DESISTIU",
        "PAGODIRETOAOCLIENTE",
        "SUBSTITUICAO",
    }
)

DEFAULT_INTER_CANCEL_MOTIVO = "ACERTOS"
