"""ensure_services_for_wizard — catálogo do select Serviço no wizard NFS-e."""

from __future__ import annotations

import pytest

from apps.master_data.models import ServiceCatalogItem
from apps.master_data.services import ensure_services_for_wizard


@pytest.mark.django_db
def test_ensure_services_seeds_when_tenant_catalog_empty(tenant_a):
    assert ServiceCatalogItem.objects.filter(tenant=tenant_a).count() == 0
    services = ensure_services_for_wizard(tenant=tenant_a)
    assert len(services) >= 3
    codes = {s.service_code for s in services}
    assert "01.07" in codes
    assert "17.19" in codes
    # idempotente
    again = ensure_services_for_wizard(tenant=tenant_a)
    assert len(again) == len(services)
    assert ServiceCatalogItem.objects.filter(tenant=tenant_a).count() == len(services)


@pytest.mark.django_db
def test_ensure_services_keeps_existing(tenant_a):
    ServiceCatalogItem.objects.create(
        tenant=tenant_a,
        service_code="99.01",
        description="Serviço custom",
        lc116_item="99.01",
        is_active=True,
    )
    services = ensure_services_for_wizard(tenant=tenant_a)
    assert len(services) == 1
    assert services[0].service_code == "99.01"
