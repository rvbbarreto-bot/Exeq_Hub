"""Feature flag NF-e de entrada."""

from __future__ import annotations

import pytest

from apps.nfe.entrada.exceptions import NfeEntradaDisabledError
from apps.nfe.entrada.feature import (
    nfe_entrada_enabled_for_tenant,
    nfe_entrada_global_enabled,
    require_nfe_entrada_enabled,
)


@pytest.mark.django_db
def test_global_disabled_by_default(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = False
    assert nfe_entrada_global_enabled() is False
    assert nfe_entrada_enabled_for_tenant(tenant_a) is False


@pytest.mark.django_db
def test_tenant_opt_in_required(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = True
    tenant_a.settings = {}
    tenant_a.save(update_fields=["settings"])
    assert nfe_entrada_enabled_for_tenant(tenant_a) is False

    tenant_a.settings = {"nfe_entrada_enabled": True}
    tenant_a.save(update_fields=["settings"])
    assert nfe_entrada_enabled_for_tenant(tenant_a) is True


@pytest.mark.django_db
def test_require_raises_when_disabled(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = False
    with pytest.raises(NfeEntradaDisabledError):
        require_nfe_entrada_enabled(tenant=tenant_a)


def test_exceptions_custom_codes():
    from apps.nfe.entrada.exceptions import ConsumptionLimitError, ManifestationError

    exc = ManifestationError("falha", code="custom")
    assert exc.code == "custom"
    assert ConsumptionLimitError().code == "nfe_entrada_consumption_limit"
