"""Testes do comando food_mp_check."""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.food.onboarding import onboard_food_qa_tenant


@pytest.mark.django_db
def test_food_mp_check_stub_passes(settings, tmp_path):
    settings.FOOD_MP_HTTP_MODE = "stub"
    settings.FOOD_MP_WEBHOOK_SECRET = "mp-webhook-test-secret"
    settings.FIELD_ENCRYPTION_KEY = "n_AQ8FIJHEVdMys3lkm17BygqS8UkBCEfRtzlNaZhhw="
    onboard_food_qa_tenant(mp_webhook_secret="mp-webhook-test-secret")
    out = tmp_path / "mp_check.json"
    call_command("food_mp_check", "--tenant", "food-qa", "--out", str(out), "--strict")
    assert out.is_file()
