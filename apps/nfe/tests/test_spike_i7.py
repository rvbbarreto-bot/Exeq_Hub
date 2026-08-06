"""I7 — nfe_spike_sefaz stub/dry-run sem rede."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.models import NfeInvoice


@pytest.fixture
def provider_lab(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ SPIKE LAB",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        state_registration="",
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


@pytest.mark.django_db
def test_spike_stub_no_network(tmp_path, tenant_a, provider_lab):
    out = tmp_path / "ev.json"
    call_command(
        "nfe_spike_sefaz",
        tenant=tenant_a.slug,
        cnpj="37229907000137",
        mode="stub",
        out=str(out),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == NfeInvoice.Status.AUTHORIZED
    assert data["g_spike_candidate"] is False
    assert data["mode"] == "stub"
    assert "password" not in json.dumps(data)
    assert data["nfe_enabled_prod_default"] is False
    inv = NfeInvoice.objects.get(id=data["invoice_id"])
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert len(inv.access_key) == 44


@pytest.mark.django_db
def test_spike_http_dry_run_no_post(tmp_path, tenant_a, provider_lab, settings):
    # IE exigida em modo http (validate); dry-run ainda não POST SEFAZ.
    provider_lab.state_registration = "123456789112"
    provider_lab.save(update_fields=["state_registration"])
    out = tmp_path / "ev-dry.json"
    call_command(
        "nfe_spike_sefaz",
        tenant=tenant_a.slug,
        cnpj="37229907000137",
        mode="http",
        dry_run=True,
        out=str(out),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["dry_run"] is True
    assert data["g_spike_candidate"] is False
    # sem A1: CERT; com dry-run e cert fake: DRY_RUN — qualquer falha sem authorized
    assert data["status"] != NfeInvoice.Status.AUTHORIZED
    assert data["status"] in {
        NfeInvoice.Status.FAILED,
        NfeInvoice.Status.REJECTED,
    }


@pytest.mark.django_db
def test_spike_missing_provider(tenant_a):
    with pytest.raises(CommandError, match="Provider"):
        call_command(
            "nfe_spike_sefaz",
            tenant=tenant_a.slug,
            cnpj="00000000000191",
            mode="stub",
            out=str(Path("/tmp/nfe-spike-x.json")),
        )
