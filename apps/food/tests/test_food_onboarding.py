"""Testes do onboarding Food QA."""

from __future__ import annotations

import pytest

from apps.accounts.models import Tenant, TenantMembership, User
from apps.food.models import FoodCustomer, FoodProduct
from apps.food.onboarding import onboard_food_qa_tenant


@pytest.mark.django_db
def test_onboard_food_qa_idempotent():
    first = onboard_food_qa_tenant(mp_webhook_secret="mp-webhook-test-secret")
    second = onboard_food_qa_tenant(mp_webhook_secret="mp-webhook-test-secret")

    assert first.tenant_slug == "food-qa"
    assert first.created["tenant"] is True
    assert first.created["user"] is True
    assert first.created["product"] is True

    assert second.created["tenant"] is False
    assert second.created["user"] is False
    assert second.created["product"] is False

    tenant = Tenant.objects.get(slug="food-qa")
    assert tenant.settings["food_payment_provider"] == "mercadopago"
    assert tenant.settings["food_payment_methods_enabled"] == ["pix", "card"]

    user = User.objects.get(email="qa.food@exeq.local")
    assert user.check_password("Secret123!")
    assert TenantMembership.objects.filter(tenant=tenant, user=user, is_active=True).exists()

    assert FoodCustomer.objects.filter(tenant=tenant, email="maria.qa@example.com").exists()
    assert FoodProduct.objects.filter(tenant=tenant, sku="QA-FOOD-01").exists()

    from apps.accounts.secrets import get_tenant_secret_plaintext

    assert (
        get_tenant_secret_plaintext(
            tenant=tenant,
            provider="mercadopago",
            key_name="webhook_secret",
        )
        == "mp-webhook-test-secret"
    )
