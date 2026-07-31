"""Mapeamento situacao Inter Cobrança v3 → status Hub."""

from __future__ import annotations

from typing import Any

from apps.billing.models import Charge

# Inter → Hub
INTER_SITUACAO_TO_HUB = {
    "EM_PROCESSAMENTO": Charge.Status.PENDING,
    "A_RECEBER": Charge.Status.REGISTERED,
    "ATRASADO": Charge.Status.OVERDUE,
    "RECEBIDO": Charge.Status.PAID,
    "MARCADO_RECEBIDO": Charge.Status.PAID,
    "CANCELADO": Charge.Status.CANCELLED,
    "EXPIRADO": Charge.Status.CANCELLED,
    "FALHA_EMISSAO": Charge.Status.FAILED,
}


def extract_inter_cobranca(payload: dict[str, Any]) -> dict[str, Any]:
    cob = payload.get("cobranca")
    if isinstance(cob, dict):
        return cob
    return payload


def map_inter_situacao(situacao: str | None) -> str | None:
    key = (situacao or "").strip().upper()
    return INTER_SITUACAO_TO_HUB.get(key)


def inter_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    cobranca = extract_inter_cobranca(payload)
    boleto = cobranca.get("boleto") or payload.get("boleto") or {}
    pix = cobranca.get("pix") or payload.get("pix") or {}
    if not isinstance(boleto, dict):
        boleto = {}
    if not isinstance(pix, dict):
        pix = {}
    valor = cobranca.get("valorNominal")
    amount_cents = None
    if valor is not None:
        try:
            amount_cents = int(round(float(valor) * 100))
        except (TypeError, ValueError):
            amount_cents = None
    valor_recebido = cobranca.get("valorTotalRecebido") or cobranca.get(
        "valorTotalRecebimento"
    )
    received_cents = None
    if valor_recebido is not None:
        try:
            received_cents = int(round(float(valor_recebido) * 100))
        except (TypeError, ValueError):
            received_cents = None
    return {
        "situacao": (cobranca.get("situacao") or "").strip().upper(),
        "data_situacao": cobranca.get("dataSituacao") or cobranca.get("dataHoraSituacao"),
        "seu_numero": cobranca.get("seuNumero") or "",
        "digitable_line": boleto.get("linhaDigitavel") or "",
        "barcode": boleto.get("codigoBarras") or "",
        "pix_copy_paste": pix.get("pixCopiaECola") or "",
        "amount_cents": amount_cents,
        "received_cents": received_cents,
        "codigo_solicitacao": cobranca.get("codigoSolicitacao") or "",
        "origem_recebimento": cobranca.get("origemRecebimento") or "",
    }
