"""Orçamentos de tempo SEFIN → Celery (SEC-P2-04).

Garante que latência/5xx com retry não prendam o worker além de um teto calculável.
"""

from __future__ import annotations

from django.conf import settings


def sefin_http_wall_budget_seconds(
    *,
    timeout: float,
    max_attempts: int,
    backoff_seconds: float,
) -> float:
    """Pior caso de uma chamada HTTP com retries (tentativas + sleeps entre elas)."""
    attempts = max(1, int(max_attempts))
    timeout = max(0.0, float(timeout))
    backoff = max(0.0, float(backoff_seconds))
    # sleeps: backoff*1 + backoff*2 + ... + backoff*(attempts-1)
    sleeps = backoff * (attempts - 1) * attempts / 2.0
    return attempts * timeout + sleeps


def nf_issue_process_time_limits(
    *,
    timeout: float | None = None,
    max_attempts: int | None = None,
    backoff_seconds: float | None = None,
    http_round_trips: int = 2,
    slack_seconds: float = 60.0,
    hard_extra_seconds: float = 30.0,
) -> tuple[int, int]:
    """(soft_time_limit, time_limit) para `issuance.process_nf_issue`.

    Default: até 2 round-trips SEFIN (emit + eventual consulta) + folga.
    """
    timeout = float(
        timeout
        if timeout is not None
        else getattr(settings, "SEFIN_HTTP_TIMEOUT_SECONDS", 45.0)
    )
    max_attempts = int(
        max_attempts
        if max_attempts is not None
        else getattr(settings, "SEFIN_HTTP_MAX_ATTEMPTS", 3)
    )
    backoff_seconds = float(
        backoff_seconds
        if backoff_seconds is not None
        else getattr(settings, "SEFIN_HTTP_RETRY_BACKOFF_SECONDS", 0.5)
    )
    trips = max(1, int(http_round_trips))
    one = sefin_http_wall_budget_seconds(
        timeout=timeout,
        max_attempts=max_attempts,
        backoff_seconds=backoff_seconds,
    )
    soft = int(one * trips + max(0.0, slack_seconds))
    hard = soft + int(max(1.0, hard_extra_seconds))
    return max(soft, 30), max(hard, soft + 1)


def resolve_process_time_limits() -> tuple[int, int]:
    """Lê override de env/settings ou calcula a partir do budget HTTP."""
    soft_ov = getattr(settings, "NFSE_PROCESS_SOFT_TIME_LIMIT", None)
    hard_ov = getattr(settings, "NFSE_PROCESS_HARD_TIME_LIMIT", None)
    if soft_ov is not None and hard_ov is not None:
        soft_i, hard_i = int(soft_ov), int(hard_ov)
        if soft_i > 0 and hard_i > soft_i:
            return soft_i, hard_i
    return nf_issue_process_time_limits()


def resolve_poll_time_limits() -> tuple[int, int]:
    soft_ov = getattr(settings, "NFSE_POLL_SOFT_TIME_LIMIT", None)
    hard_ov = getattr(settings, "NFSE_POLL_HARD_TIME_LIMIT", None)
    if soft_ov is not None and hard_ov is not None:
        soft_i, hard_i = int(soft_ov), int(hard_ov)
        if soft_i > 0 and hard_i > soft_i:
            return soft_i, hard_i
    # Um GET com retries + folga menor.
    return nf_issue_process_time_limits(http_round_trips=1, slack_seconds=30.0)
