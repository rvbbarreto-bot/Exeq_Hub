"""Motivos cMotivo (evento e101101) e validação de justificativa de cancelamento NFS-e."""

from __future__ import annotations

NFSE_CANCEL_JUSTIFICATIVA_MIN = 15
NFSE_CANCEL_JUSTIFICATIVA_MAX = 150

# Manual SEFIN / ADN: 1 erro emissão, 2 serviço não prestado, 9 outros (Hub expõe estes três).
NFSE_CANCEL_MOTIVOS: tuple[tuple[int, str], ...] = (
    (1, "Erro na emissão"),
    (2, "Serviço não prestado"),
    (9, "Outros"),
)

ALLOWED_CMOTIVO: frozenset[int] = frozenset(code for code, _ in NFSE_CANCEL_MOTIVOS)


def parse_codigo_cancelamento(value: object) -> int:
    if value is None or value == "":
        raise ValueError("Selecione o motivo do cancelamento.")
    try:
        code = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Motivo de cancelamento inválido.") from exc
    if code not in ALLOWED_CMOTIVO:
        raise ValueError("Motivo de cancelamento inválido.")
    return code


def validate_justificativa(text: str) -> str:
    cleaned = (text or "").strip()
    n = len(cleaned)
    if n < NFSE_CANCEL_JUSTIFICATIVA_MIN:
        raise ValueError(
            f"A justificativa deve ter no mínimo {NFSE_CANCEL_JUSTIFICATIVA_MIN} caracteres."
        )
    if n > NFSE_CANCEL_JUSTIFICATIVA_MAX:
        raise ValueError(
            f"A justificativa deve ter no máximo {NFSE_CANCEL_JUSTIFICATIVA_MAX} caracteres."
        )
    return cleaned
