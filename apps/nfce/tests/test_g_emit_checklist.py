"""G-EMIT-NFCE checklist — gate + env."""

from __future__ import annotations

import pytest

from apps.accounts.tenant_emission import apply_emission_flags
from apps.master_data.models import Provider, TaxRegime
from apps.nfce.g_emit_checklist import build_g_emit_checklist


@pytest.mark.django_db
def test_g_emit_checklist_stub_mode(settings, tenant_a):
    settings.NFCE_ENABLED = True
    settings.NFCE_HTTP_MODE = "stub"
    tenant_a.settings = apply_emission_flags(
        tenant_a.settings, nfse=True, nfe=True, nfce=True
    )
    tenant_a.save(update_fields=["settings"])
    provider = Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="G-EMIT NFCe",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )
    payload = build_g_emit_checklist(tenant=tenant_a, provider_id=str(provider.id))
    assert payload["purpose"] == "g_emit_nfce_checklist"
    assert payload["ready_for_http_dry_run"] is False
    assert "http_mode" in payload["blockers"]
