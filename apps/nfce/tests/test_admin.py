"""Admin NFC-e — registro TenantCscToken."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from apps.master_data.models import Provider, TaxRegime
from apps.nfce.admin import TenantCscTokenAdmin
from apps.nfce.models import TenantCscToken


@pytest.mark.django_db
def test_csc_token_masked_display(tenant_a):
    provider = Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="Admin CSC",
        tax_regime=TaxRegime.SIMPLES,
        address={"uf": "SP"},
        is_active=True,
    )
    row = TenantCscToken.objects.create(
        tenant=tenant_a,
        provider=provider,
        tp_amb="2",
        csc_id="1",
        csc_token="SECRETTOKEN",
        is_active=True,
    )
    admin = TenantCscTokenAdmin(TenantCscToken, AdminSite())
    masked = admin.csc_token_masked(row)
    assert masked.startswith("SE")
    assert masked.endswith("EN")
    assert "SECRETTOKEN" not in masked
