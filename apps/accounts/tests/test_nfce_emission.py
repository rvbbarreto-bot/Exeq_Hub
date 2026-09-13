"""Testes nfce_enabled_for_tenant."""

import pytest

from apps.accounts.tenant_emission import nfce_enabled_for_tenant


@pytest.mark.django_db
def test_nfce_enabled_requires_global_and_tenant(settings, tenant_a):
    settings.NFCE_ENABLED = False
    tenant_a.settings = {"nfce_enabled": True}
    tenant_a.save(update_fields=["settings"])
    assert nfce_enabled_for_tenant(tenant_a) is False

    settings.NFCE_ENABLED = True
    assert nfce_enabled_for_tenant(tenant_a) is True
