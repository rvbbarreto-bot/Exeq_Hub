"""Testes do comando fiscal_import_rules_csv."""

from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.fiscal.models import FiscalProfile
from apps.master_data.models import TaxRegime
from apps.master_data.services import create_provider


@pytest.fixture
def csv_cmd_ctx(tenant_a):
    tenant_a.slug = "csv-cmd-tenant"
    tenant_a.save(update_fields=["slug"])
    create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="Prest CSV",
        tax_regime=TaxRegime.SIMPLES,
    )
    profile = FiscalProfile.objects.create(
        tenant=tenant_a, name="SN-CSV", tax_regime=TaxRegime.SIMPLES, status="active"
    )
    return {"tenant": tenant_a, "profile": profile}


@pytest.mark.django_db
def test_fiscal_import_rules_csv_dry_run(tmp_path, csv_cmd_ctx):
    csv_path = tmp_path / "rules.csv"
    csv_path.write_text(
        "service_code,ibge_code,iss_rate\n01.07,3550308,0.05\n",
        encoding="utf-8",
    )
    call_command(
        "fiscal_import_rules_csv",
        tenant=csv_cmd_ctx["tenant"].slug,
        fiscal_profile=csv_cmd_ctx["profile"].name,
        file=str(csv_path),
        dry_run=True,
    )


@pytest.mark.django_db
def test_fiscal_import_rules_csv_import(tmp_path, csv_cmd_ctx):
    csv_path = tmp_path / "rules.csv"
    csv_path.write_text(
        "service_code,ibge_code,iss_rate,municipio_nome,uf\n"
        "01.07,3550308,0.05,São Paulo,SP\n",
        encoding="utf-8",
    )
    out = tmp_path / "result.json"
    call_command(
        "fiscal_import_rules_csv",
        tenant=csv_cmd_ctx["tenant"].slug,
        fiscal_profile=csv_cmd_ctx["profile"].name,
        file=str(csv_path),
        out=str(out),
    )
    assert out.is_file()
    assert "3550308" in out.read_text(encoding="utf-8")
