"""I5 — consultar recibo/chave + poll FSM (sem rede SEFAZ)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.models import NfeInvoice, NfeNumberSeries
from apps.nfe.polling import poll_nfe_invoice
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items
from integrations.sefaz_nfe.parse import map_cstat_to_status, parse_autorizacao_response
from integrations.sefaz_nfe.port import HttpNfeProvider, NfeEmitResult, StubNfeProvider
from integrations.sefaz_nfe.transport import (
    SefazHttpResponse,
    build_cons_reci_nfe,
    build_cons_sit_nfe,
)

_FIXTURE_RET_AUTORIZADA = """<?xml version="1.0" encoding="UTF-8"?>
<retConsReciNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <tpAmb>2</tpAmb>
  <nRec>123456789012345</nRec>
  <cStat>104</cStat>
  <xMotivo>Lote processado</xMotivo>
  <protNFe versao="4.00">
    <infProt>
      <chNFe>35260837229907000137550010000000011000000010</chNFe>
      <nProt>135260000000099</nProt>
      <cStat>100</cStat>
      <xMotivo>Autorizado o uso da NF-e</xMotivo>
    </infProt>
  </protNFe>
</retConsReciNFe>
"""

_FIXTURE_RET_PROCESSANDO = """<?xml version="1.0" encoding="UTF-8"?>
<retConsReciNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <tpAmb>2</tpAmb>
  <cStat>105</cStat>
  <xMotivo>Lote em processamento</xMotivo>
</retConsReciNFe>
"""

_FIXTURE_LOTE_103 = """<?xml version="1.0" encoding="UTF-8"?>
<retEnviNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <tpAmb>2</tpAmb>
  <cStat>103</cStat>
  <xMotivo>Lote recebido com sucesso</xMotivo>
  <infRec>
    <nRec>123456789012345</nRec>
  </infRec>
</retEnviNFe>
"""


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    settings.NFE_POLL_MAX_ATTEMPTS = 3
    settings.NFE_SYNC_POLL = False
    settings.CELERY_TASK_ALWAYS_EAGER = False
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        state_registration="",
        address={
            "logradouro": "Rua Jose Florido",
            "numero": "121",
            "bairro": "Jardim Alvinopolis",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente B2B",
        address={
            "logradouro": "Av Teste",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


def test_parse_lote_103_extracts_n_rec():
    p = parse_autorizacao_response(_FIXTURE_LOTE_103)
    assert p.c_stat == "103"
    assert p.n_rec == "123456789012345"
    assert map_cstat_to_status(p.c_stat) == "polling"


def test_parse_ret_cons_reci_prefers_infprot():
    p = parse_autorizacao_response(_FIXTURE_RET_AUTORIZADA)
    assert p.c_stat == "100"
    assert p.lote_c_stat == "104"
    assert p.protocol == "135260000000099"
    assert p.n_rec == "123456789012345"
    assert map_cstat_to_status(p.c_stat) == "authorized"


def test_parse_ret_105_polling():
    p = parse_autorizacao_response(_FIXTURE_RET_PROCESSANDO)
    assert p.c_stat == "105"
    assert map_cstat_to_status(p.c_stat) == "polling"


def test_build_cons_payloads():
    assert "nRec>123" in build_cons_reci_nfe(tp_amb="2", n_rec="123")
    assert "chNFe>3526" in build_cons_sit_nfe(tp_amb="2", access_key="3526" + "0" * 40)


def test_stub_consultar():
    r = StubNfeProvider().consultar(access_key="1" * 44, receipt="99")
    assert r.status == "authorized"
    assert r.access_key == "1" * 44


def test_stub_consultar_missing_ref():
    r = StubNfeProvider().consultar()
    assert r.status == "failed"
    assert r.rejection_code == "REF"


@pytest.mark.django_db
def test_http_consultar_by_receipt(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = False
    authorized = SefazHttpResponse(
        http_status=200,
        body=_FIXTURE_RET_AUTORIZADA,
        c_stat="100",
        x_motivo="Autorizado o uso da NF-e",
        protocol="135260000000099",
        access_key="35260837229907000137550010000000011000000010",
        lote_c_stat="104",
        n_rec="123456789012345",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_ret_autorizacao",
            return_value=authorized,
        ) as ret_mock,
        patch("integrations.sefaz_nfe.transport.post_nfe_consulta_protocolo") as cons_mock,
    ):
        r = HttpNfeProvider().consultar(
            receipt="123456789012345",
            tp_amb="2",
            context={"tenant": tenant_a, "cnpj": "37229907000137"},
        )
    ret_mock.assert_called_once()
    cons_mock.assert_not_called()
    assert r.status == "authorized"
    assert r.protocol == "135260000000099"


@pytest.mark.django_db
def test_http_consultar_by_access_key_fallback(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = False
    authorized = SefazHttpResponse(
        http_status=200,
        body=_FIXTURE_RET_AUTORIZADA,
        c_stat="100",
        x_motivo="Autorizado",
        protocol="1",
        access_key="35260837229907000137550010000000011000000010",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "")),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_consulta_protocolo",
            return_value=authorized,
        ) as cons_mock,
        patch("integrations.sefaz_nfe.transport.post_nfe_ret_autorizacao") as ret_mock,
    ):
        r = HttpNfeProvider().consultar(
            access_key="35260837229907000137550010000000011000000010",
            tp_amb="2",
            context={"tenant": tenant_a, "cnpj": "37229907000137"},
        )
    cons_mock.assert_called_once()
    ret_mock.assert_not_called()
    assert r.status == "authorized"


def _seed_polling_invoice(tenant_a, provider_sp, customer_b2b, *, number: int = 7):
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key=f"poll-{number}",
    )
    product = create_product(
        tenant=tenant_a,
        code=f"SKU-P{number}",
        description="Produto poll",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    inv.status = NfeInvoice.Status.POLLING
    inv.number = number
    inv.number_consumed = True
    inv.access_key = "35260837229907000137550010000000011000000010"
    inv.total_cents = 1000
    inv.issue_date = date(2026, 8, 5)
    inv.fiscal_snapshot = {
        "emitente": {
            "cnpj": "37229907000137",
            "name": "EXEQ",
            "crt": "simples_nacional",
            "address": provider_sp.address,
        },
        "header": {
            "series": inv.series,
            "number": number,
            "tp_amb": "2",
            "issue_date": "2026-08-05",
        },
        "items": [
            {
                "line": 1,
                "code": "SKU",
                "description": "P",
                "ncm": "21069090",
                "cfop": "5102",
                "unit": "UN",
                "quantity": "1",
                "unit_price_cents": 1000,
                "total_cents": 1000,
                "origin": "0",
                "csosn": "102",
                "taxes": {},
            }
        ],
        "totals": {"total_cents": 1000, "products_cents": 1000},
        "payment": {"method": "99", "amount_cents": 1000},
        "sefaz": {"n_rec": "123456789012345", "poll_attempts": 0},
    }
    inv.save()
    # Série já consumiu o número no emit real — espelhamos next_number = number+1
    NfeNumberSeries.objects.update_or_create(
        tenant=tenant_a,
        provider=provider_sp,
        series=inv.series,
        tp_amb=inv.tp_amb,
        defaults={"next_number": number + 1, "is_active": True},
    )
    return inv


@pytest.mark.django_db
def test_poll_fsm_polling_to_authorized_no_number_reentry(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _seed_polling_invoice(tenant_a, provider_sp, customer_b2b, number=7)
    series_before = NfeNumberSeries.objects.get(
        tenant=tenant_a, provider=provider_sp, series=inv.series, tp_amb=inv.tp_amb
    ).next_number

    result = poll_nfe_invoice(inv)
    assert result.status == NfeInvoice.Status.AUTHORIZED
    assert result.number == 7
    assert result.number_consumed is True
    assert result.protocol.startswith("STUBPOLL")
    series_after = NfeNumberSeries.objects.get(
        tenant=tenant_a, provider=provider_sp, series=inv.series, tp_amb=inv.tp_amb
    ).next_number
    assert series_after == series_before  # sem reentrada


@pytest.mark.django_db
def test_poll_fsm_exhausted_to_failed(nfe_settings, tenant_a, provider_sp, customer_b2b):
    nfe_settings.NFE_POLL_MAX_ATTEMPTS = 2
    inv = _seed_polling_invoice(tenant_a, provider_sp, customer_b2b, number=3)
    snap = dict(inv.fiscal_snapshot)
    snap["sefaz"] = {"n_rec": "1", "poll_attempts": 2}
    inv.fiscal_snapshot = snap
    inv.save(update_fields=["fiscal_snapshot"])

    with patch(
        "apps.nfe.polling.get_nfe_provider",
        return_value=StubNfeProvider(),
    ):
        # attempts already 2; next call goes to 3 > 2 without depend on stub stay
        result = poll_nfe_invoice(inv)

    assert result.status == NfeInvoice.Status.FAILED
    assert result.rejection_code == "POLL_EXHAUSTED"
    assert result.number == 3
    assert result.number_consumed is True


@pytest.mark.django_db
def test_poll_stays_polling_when_provider_polling(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    inv = _seed_polling_invoice(tenant_a, provider_sp, customer_b2b, number=4)

    class PollingProvider:
        kind = "mock"

        def consultar(self, **kwargs):
            return NfeEmitResult(
                status="polling",
                access_key=kwargs.get("access_key") or "",
                rejection_code="105",
                rejection_message="Lote em processamento",
                raw={"cStat": "105", "nRec": "123"},
            )

    with patch("apps.nfe.polling.get_nfe_provider", return_value=PollingProvider()):
        result = poll_nfe_invoice(inv)

    assert result.status == NfeInvoice.Status.POLLING
    assert (result.fiscal_snapshot or {}).get("sefaz", {}).get("poll_attempts") == 1
    assert result.number_consumed is True


@pytest.mark.django_db
def test_poll_rejects_fsm(nfe_settings, tenant_a, provider_sp, customer_b2b):
    inv = _seed_polling_invoice(tenant_a, provider_sp, customer_b2b, number=5)

    class RejectProvider:
        kind = "mock"

        def consultar(self, **kwargs):
            return NfeEmitResult(
                status="rejected",
                access_key=kwargs.get("access_key") or "",
                rejection_code="204",
                rejection_message="Duplicidade",
                raw={"cStat": "204"},
            )

    with patch("apps.nfe.polling.get_nfe_provider", return_value=RejectProvider()):
        result = poll_nfe_invoice(inv)

    assert result.status == NfeInvoice.Status.REJECTED
    assert result.rejection_code == "204"
    assert result.number_consumed is True


@pytest.mark.django_db
def test_emit_schedules_poll_on_polling_result(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    product = create_product(
        tenant=tenant_a,
        code="SKU-EMIT-P",
        description="Produto",
        ncm="21069090",
        unit_price_cents=5000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="emit-poll-1",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])

    class PollingEmitProvider:
        kind = "mock"

        def emitir(self, **kwargs):
            return NfeEmitResult(
                status="polling",
                access_key="35260837229907000137550010000000011000000010",
                rejection_code="103",
                rejection_message="Lote recebido",
                raw={"cStat": "103", "nRec": "999888777666555"},
            )

        def consultar(self, **kwargs):
            return NfeEmitResult(status="authorized", access_key=kwargs.get("access_key") or "")

        def cancelar(self, **kwargs):
            return NfeEmitResult(status="failed", rejection_code="N/A")

    with (
        patch("apps.nfe.services.get_nfe_provider", return_value=PollingEmitProvider()),
        patch("apps.nfe.polling.schedule_nfe_poll") as sched,
    ):
        emit_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.POLLING
    assert inv.number_consumed is True
    assert inv.fiscal_snapshot["sefaz"]["n_rec"] == "999888777666555"
    sched.assert_called_once()
