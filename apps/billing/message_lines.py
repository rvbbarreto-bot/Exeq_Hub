"""Mensagem do boleto Inter: até 5 linhas × 78 caracteres."""

from __future__ import annotations

MESSAGE_LINE_MAX = 78
MESSAGE_LINE_COUNT = 5


def split_message_lines(
    description: str = "",
    *,
    lines: list[str] | None = None,
) -> list[str]:
    if lines is not None:
        cleaned = [str(line or "").strip()[:MESSAGE_LINE_MAX] for line in lines]
        if len(cleaned) > MESSAGE_LINE_COUNT:
            raise ValueError(
                f"mensagem permite no máximo {MESSAGE_LINE_COUNT} linhas"
            )
        while len(cleaned) < MESSAGE_LINE_COUNT:
            cleaned.append("")
        if not any(cleaned):
            cleaned[0] = "Cobranca EXEQ Hub"
        return cleaned[:MESSAGE_LINE_COUNT]

    text = (description or "").strip() or "Cobranca EXEQ Hub"
    result: list[str] = []
    remaining = text
    while remaining and len(result) < MESSAGE_LINE_COUNT:
        result.append(remaining[:MESSAGE_LINE_MAX])
        remaining = remaining[MESSAGE_LINE_MAX:].lstrip()
    while len(result) < MESSAGE_LINE_COUNT:
        result.append("")
    return result


def message_lines_to_inter(lines: list[str]) -> dict[str, str]:
    padded = split_message_lines(lines=lines)
    return {f"linha{i}": padded[i - 1] for i in range(1, MESSAGE_LINE_COUNT + 1)}
