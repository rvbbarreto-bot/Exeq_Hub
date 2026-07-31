"""SEC-P2-04: budget de tempo SEFIN → Celery."""

from integrations.nfse.resilience import (
    nf_issue_process_time_limits,
    resolve_poll_time_limits,
    resolve_process_time_limits,
    sefin_http_wall_budget_seconds,
)


def test_sefin_http_wall_budget_accounts_retries():
    # 3 * 45 + 0.5*(1+2) = 135 + 1.5
    assert sefin_http_wall_budget_seconds(
        timeout=45.0, max_attempts=3, backoff_seconds=0.5
    ) == 136.5


def test_nf_issue_process_time_limits_default_covers_two_trips():
    soft, hard = nf_issue_process_time_limits(
        timeout=45.0, max_attempts=3, backoff_seconds=0.5
    )
    assert soft >= 136.5 * 2 + 60
    assert hard > soft


def test_resolve_process_time_limits_override(settings):
    settings.NFSE_PROCESS_SOFT_TIME_LIMIT = 120
    settings.NFSE_PROCESS_HARD_TIME_LIMIT = 150
    assert resolve_process_time_limits() == (120, 150)


def test_resolve_poll_time_limits_one_trip(settings):
    settings.NFSE_POLL_SOFT_TIME_LIMIT = None
    settings.NFSE_POLL_HARD_TIME_LIMIT = None
    soft, hard = resolve_poll_time_limits()
    soft2, hard2 = nf_issue_process_time_limits(http_round_trips=1, slack_seconds=30.0)
    assert (soft, hard) == (soft2, hard2)


def test_process_nf_issue_task_has_time_limits():
    from apps.issuance.tasks import process_nf_issue

    assert process_nf_issue.soft_time_limit is not None
    assert process_nf_issue.time_limit is not None
    assert process_nf_issue.time_limit > process_nf_issue.soft_time_limit
