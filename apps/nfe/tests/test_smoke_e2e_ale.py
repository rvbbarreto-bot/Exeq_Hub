"""Fase 3 — smoke E2E stub ALE (emit + XML + DANFE + compare)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.models import Tenant
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.homolog_spike import ALE_CNPJ, run_smoke_e2e
from apps.nfe.models import NfeInvoice
from integrations.sefaz_nfe.danfe.compare import StructuralCompareResult


@pytest.fixture
def ale_tenant(db, settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    return Tenant.objects.create(
        slug="ALE",
        legal_name="ALE Piloto",
        document=ALE_CNPJ,
        settings={"nfe_enabled": True},
    )


@pytest.fixture
def ale_provider(ale_tenant):
    return Provider.objects.create(
        tenant=ale_tenant,
        document=ALE_CNPJ,
        legal_name="ALE Emitente",
        tax_regime=TaxRegime.SIMPLES,
        state_registration="123456789112",
        address={
            "logradouro": "Rua Piloto",
            "numero": "100",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )


@pytest.fixture
def ale_customer(ale_tenant):
    return Customer.objects.create(
        tenant=ale_tenant,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente ALE",
        address={
            "logradouro": "Av Cliente",
            "numero": "1",
            "uf": "SP",
            "codigo_ibge": "3504107",
        },
    )


@pytest.mark.django_db
def test_smoke_e2e_stub_homolog(ale_tenant, ale_provider, ale_customer, settings):
    settings.NFE_ENABLED = True
    result = run_smoke_e2e(
        tenant=ale_tenant,
        provider=ale_provider,
        customer=ale_customer,
        mode="stub",
        tp_amb="2",
    )
    assert result["smoke_ok"] is True
    assert result["status"] == NfeInvoice.Status.AUTHORIZED
    assert result["xml_authorized"] is True
    assert result["danfe_pdf"] is True
    assert result["structural_ok"] is True
    assert result["structural_missing"] == []


def test_smoke_e2e_pipeline_mocked():
    """Valida agregação smoke sem Postgres (DB tests abaixo)."""
    inv = MagicMock()
    inv.id = "inv-smoke-1"
    inv.status = NfeInvoice.Status.AUTHORIZED
    inv.access_key = "35250961536366000174550010000000011234567890"
    tenant = MagicMock(slug="ALE")
    provider = MagicMock(document=ALE_CNPJ)
    customer = MagicMock()

    pdf_art = MagicMock()
    with (
        patch("apps.nfe.homolog_spike.build_homolog_preflight", return_value={"ok": True, "blockers": []}),
        patch("apps.nfe.homolog_spike.run_homolog_spike", return_value=(inv, {})),
        patch("apps.nfe.artifacts.ensure_authorized_artifacts", return_value=[pdf_art]),
        patch("apps.nfe.artifacts.get_artifact", return_value=pdf_art),
        patch("apps.nfe.artifacts.read_artifact_bytes", return_value=b"%PDF-mock"),
        patch("apps.nfe.artifacts.has_xml_authorized", return_value=True),
        patch("apps.nfe.artifacts.has_danfe_pdf", return_value=True),
        patch(
            "integrations.sefaz_nfe.danfe.compare.compare_structural",
            return_value=StructuralCompareResult(passed={"DANFE": True}, missing=(), page_count=1),
        ),
    ):
        result = run_smoke_e2e(
            tenant=tenant,
            provider=provider,
            customer=customer,
            mode="stub",
            tp_amb="2",
        )

    assert result["smoke_ok"] is True
    assert result["structural_ok"] is True
    assert result["structural_missing"] == []
    assert result["tp_amb"] == "2"


@pytest.mark.django_db
def test_smoke_e2e_production_tp_amb_stub_mode(ale_tenant, ale_provider, ale_customer, settings):
    """tpAmb=1 em stub valida pipeline sem SEFAZ real."""
    settings.NFE_ENABLED = True
    result = run_smoke_e2e(
        tenant=ale_tenant,
        provider=ale_provider,
        customer=ale_customer,
        mode="stub",
        tp_amb="1",
    )
    assert result["tp_amb"] == "1"
    assert result["smoke_ok"] is True
