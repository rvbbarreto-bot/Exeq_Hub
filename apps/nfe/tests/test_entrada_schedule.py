"""Unitários — schedule_distribuicao_sync e helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.nfe.entrada.services.distribuicao import schedule_distribuicao_sync


@pytest.mark.django_db
def test_schedule_distribuicao_sync_returns_task_id(entrada_settings, tenant_a, provider_sp):
    with patch("apps.nfe.entrada.tasks.distribuicao_sync_task.delay") as delay_mock:
        delay_mock.return_value.id = "task-abc-123"
        task_id = schedule_distribuicao_sync(tenant=tenant_a, provider=provider_sp)
    assert task_id == "task-abc-123"
    delay_mock.assert_called_once()
