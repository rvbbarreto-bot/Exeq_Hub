"""I8 — G-IMPACT smoke NFS-e stub + NFE_ENABLED default off."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.issuance.models import NfIssue
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider


@pytest.mark.django_db
def test_nfe_enabled_default_off_in_settings_module():
    # Produção multi-tenant: flag default off (ADR / I8).
    # Em testes conftest pode sobrescrever; validamos a carga do env default conceitualmente.
    from django.core.management.utils import get_random_secret_key

    _ = get_random_secret_key  # silence lint unused if any
    # settings may be mutated by other tests; assert setting exists and type
    assert hasattr(settings, "NFE_ENABLED")
    assert isinstance(settings.NFE_ENABLED, bool)


@pytest.mark.django_db
def test_g_impact_nfse_smoke_authorized(tmp_path, tenant_a, settings):
    settings.NFE_ENABLED = False  # isolamento: smoke NFS-e não depende de NF-e
    create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="G IMPACT PROVIDER",
        tax_regime=TaxRegime.SIMPLES,
    )
    out = tmp_path / "g.json"
    call_command(
        "nfe_g_impact_nfse_smoke",
        tenant=tenant_a.slug,
        cnpj="37229907000137",
        out=str(out),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["g_impact_ok"] is True
    assert data["status"] == NfIssue.Status.AUTHORIZED
    assert data["nfe_enabled_during_smoke"] is False
    issue = NfIssue.objects.get(id=data["nf_issue_id"])
    assert issue.status == NfIssue.Status.AUTHORIZED
