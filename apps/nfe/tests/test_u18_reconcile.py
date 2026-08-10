"""U18 — RF-46 reconciliação stale + RF-41 preflight XML."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice
from apps.nfe.reconciliation import reconcile_stale_nfe_batch
from integrations.sefaz_nfe.xml_nfe import build_nfe_xml
from integrations.sefaz_nfe.xml_preflight import preflight_signed_nfe


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_RECONCILE_STALE_SECONDS = 60
    settings.NFE_SYNC_POLL = False
    settings.CELERY_TASK_ALWAYS_EAGER = False
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
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


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente",
        address={
            "logradouro": "Av T",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


def _snap() -> dict:
    return {
        "emitente": {
            "cnpj": "37229907000137",
            "ie": "123456789",
            "name": "EXEQ LAB",
            "crt": "simples_nacional",
            "address": {
                "logradouro": "Rua A",
                "numero": "1",
                "bairro": "Centro",
                "municipio": "Atibaia",
                "uf": "SP",
                "cep": "12942480",
                "codigo_ibge": "3504107",
            },
        },
        "destinatario": {
            "document": "12345678909",
            "document_type": "cpf",
            "name": "Cliente",
            "address": {
                "logradouro": "Av B",
                "numero": "10",
                "bairro": "Centro",
                "municipio": "Atibaia",
                "uf": "SP",
                "cep": "12940000",
                "codigo_ibge": "3504107",
            },
        },
        "header": {
            "nature": "VENDA",
            "finality": "1",
            "series": 1,
            "number": 1,
            "tp_amb": "2",
            "issue_date": "2026-08-05",
            "ind_ie_dest": "9",
        },
        "items": [
            {
                "line": 1,
                "code": "SKU1",
                "description": "Produto",
                "ncm": "21069090",
                "cfop": "5102",
                "unit": "UN",
                "quantity": "1",
                "unit_price_cents": 1000,
                "total_cents": 1000,
                "origin": "0",
                "csosn": "102",
                "taxes": {
                    "origin": "0",
                    "icms": {"regime": "sn", "csosn": "102", "value_cents": 0},
                    "pis": {"cst": "07", "value_cents": 0, "rate_bp": 0, "base_cents": 0},
                    "cofins": {"cst": "07", "value_cents": 0, "rate_bp": 0, "base_cents": 0},
                },
            }
        ],
        "totals": {
            "products_cents": 1000,
            "total_cents": 1000,
            "freight_cents": 0,
            "discount_cents": 0,
            "icms_cents": 0,
            "pis_cents": 0,
            "cofins_cents": 0,
        },
        "payment": {"method": "99", "amount_cents": 1000},
    }


def test_preflight_accepts_unsigned_when_allowed():
    xml = build_nfe_xml(snapshot=_snap())
    ok = preflight_signed_nfe(xml, require_signature=False)
    assert ok.ok, ok.errors


def test_preflight_requires_signature_by_default():
    xml = build_nfe_xml(snapshot=_snap())
    pf = preflight_signed_nfe(xml, require_signature=True)
    assert not pf.ok
    assert "missing_Signature" in pf.errors


def test_preflight_rejects_malformed():
    pf = preflight_signed_nfe(b"<not-xml", require_signature=False)
    assert not pf.ok
    assert any(e.startswith("xml_malformed") for e in pf.errors)


def test_preflight_rejects_missing_blocks():
    bare = b'<?xml version="1.0"?><NFe xmlns="http://www.portalfiscal.inf.br/nfe"></NFe>'
    pf = preflight_signed_nfe(bare, require_signature=False)
    assert not pf.ok
    assert "missing_infNFe" in pf.errors


@pytest.mark.django_db
def test_reconcile_schedules_stale_polling(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = NfeInvoice.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        status=NfeInvoice.Status.POLLING,
        series=1,
        number=1,
        number_consumed=True,
        tp_amb="2",
        total_cents=1000,
        access_key="35260837229907000137550010000000019000000019",
        fiscal_snapshot={"sefaz": {"n_rec": "1", "poll_attempts": 0}},
        issue_date=timezone.localdate(),
    )
    NfeInvoice.objects.filter(pk=inv.pk).update(
        updated_at=timezone.now() - timedelta(seconds=300)
    )
    inv.refresh_from_db()

    with patch("apps.nfe.polling.schedule_nfe_poll") as sched:
        stats = reconcile_stale_nfe_batch(limit=10)

    assert stats["polling_scheduled"] == 1
    sched.assert_called_once()


@pytest.mark.django_db
def test_reconcile_submit_orphan_fails(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = NfeInvoice.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        status=NfeInvoice.Status.SUBMITTING,
        series=1,
        number=5,
        number_consumed=False,
        tp_amb="2",
        total_cents=1000,
        access_key="",
        fiscal_snapshot={},
        issue_date=timezone.localdate(),
    )
    NfeInvoice.objects.filter(pk=inv.pk).update(
        updated_at=timezone.now() - timedelta(seconds=300)
    )

    stats = reconcile_stale_nfe_batch(limit=10)
    inv.refresh_from_db()
    assert stats["submit_orphan"] == 1
    assert inv.status == NfeInvoice.Status.FAILED
    assert inv.rejection_code == "SUBMIT_ORPHAN"
    assert inv.number_consumed is True


@pytest.mark.django_db
def test_reconcile_submit_with_key_to_polling(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = NfeInvoice.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        status=NfeInvoice.Status.SUBMITTING,
        series=1,
        number=6,
        number_consumed=True,
        tp_amb="2",
        total_cents=1000,
        access_key="35260837229907000137550010000000019000000019",
        fiscal_snapshot={"sefaz": {"n_rec": "99"}},
        issue_date=timezone.localdate(),
    )
    NfeInvoice.objects.filter(pk=inv.pk).update(
        updated_at=timezone.now() - timedelta(seconds=300)
    )

    with patch("apps.nfe.polling.schedule_nfe_poll") as sched:
        stats = reconcile_stale_nfe_batch(limit=10)

    inv.refresh_from_db()
    assert stats["submit_to_poll"] == 1
    assert inv.status == NfeInvoice.Status.POLLING
    sched.assert_called_once()
