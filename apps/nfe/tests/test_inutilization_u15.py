"""U15 — inutilização de faixa de numeração NF-e."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.exceptions import NfeValidationError
from apps.nfe.gate import upsert_number_series
from apps.nfe.inutilization import inutilize_number_range
from apps.nfe.models import NfeInutilization, NfeInvoice, NfeNumberSeries
from apps.nfe.services import create_draft, create_product, emit_invoice, replace_items
from integrations.sefaz_nfe.endpoints import resolve_inutilizacao_url
from integrations.sefaz_nfe.inutilizacao import (
    NfeInutBuildError,
    build_inut_nfe_xml,
)
from integrations.sefaz_nfe.port import HttpNfeProvider, NfeEmitResult, StubNfeProvider
from integrations.sefaz_nfe.transport import SefazHttpResponse

_JUST = "Inutilizacao de numeros por falha de transmissao local."


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    settings.NFE_DEFAULT_TP_AMB = "2"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB",
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


def test_build_inut_xml():
    raw = build_inut_nfe_xml(
        cnpj="37229907000137",
        uf="SP",
        ano=2026,
        series=1,
        n_ini=10,
        n_fin=12,
        x_just=_JUST,
        tp_amb="2",
    )
    text = raw.decode("utf-8")
    assert "inutNFe" in text
    assert "INUTILIZAR" in text
    assert "nNFIni" in text
    assert ">10<" in text or "nNFIni>10" in text
    assert "ID35" in text


def test_build_inut_range_invalid():
    with pytest.raises(NfeInutBuildError):
        build_inut_nfe_xml(
            cnpj="37229907000137",
            uf="SP",
            ano="26",
            series=1,
            n_ini=20,
            n_fin=10,
            x_just=_JUST,
        )


def test_resolve_inutilizacao_sp():
    url = resolve_inutilizacao_url(uf="SP", tp_amb="2")
    assert "nfeinutilizacao" in url.lower()
    assert "homologacao" in url


def test_stub_inutilizar():
    r = StubNfeProvider().inutilizar(
        n_ini=1,
        n_fin=2,
        x_just=_JUST,
        context={
            "cnpj": "37229907000137",
            "uf": "SP",
            "ano": "26",
            "series": 1,
            "tp_amb": "2",
        },
    )
    assert r.status == "accepted"
    assert r.signed_xml is not None
    assert b"inutNFe" in r.signed_xml


@pytest.mark.django_db
def test_http_inut_mock_cstat_102(settings, tenant_a):
    settings.NFE_HTTP_DRY_RUN = False
    ok = SefazHttpResponse(
        http_status=200,
        body="<ok/>",
        c_stat="102",
        x_motivo="Inutilizacao de numero homologado",
        protocol="102260000000001",
    )
    with (
        patch.object(HttpNfeProvider, "_load_pfx", return_value=(b"pfx", "pwd")),
        patch(
            "integrations.sefaz_nfe.sign.sign_inut_nfe_xml",
            return_value=b"<signed-inut/>",
        ),
        patch(
            "integrations.sefaz_nfe.transport.post_nfe_inutilizacao",
            return_value=ok,
        ),
    ):
        r = HttpNfeProvider().inutilizar(
            n_ini=5,
            n_fin=5,
            x_just=_JUST,
            context={
                "tenant": tenant_a,
                "cnpj": "37229907000137",
                "uf": "SP",
                "ano": "26",
                "series": 1,
                "tp_amb": "2",
            },
        )
    assert r.status == "accepted"
    assert r.protocol == "102260000000001"


@pytest.mark.django_db
def test_domain_inutilize_advances_counter(
    nfe_settings, tenant_a, provider_sp
):
    upsert_number_series(
        tenant=tenant_a,
        provider=provider_sp,
        series=1,
        tp_amb="2",
        next_number=10,
    )
    row = inutilize_number_range(
        tenant=tenant_a,
        provider=provider_sp,
        series=1,
        tp_amb="2",
        n_ini=10,
        n_fin=12,
        x_just=_JUST,
        ano=2026,
    )
    assert row.status == NfeInutilization.Status.ACCEPTED
    series = NfeNumberSeries.objects.get(
        tenant=tenant_a, provider=provider_sp, series=1, tp_amb="2"
    )
    assert series.next_number == 13


@pytest.mark.django_db
def test_domain_inutilize_rejects_overlap_authorized(
    nfe_settings, tenant_a, provider_sp, customer_b2b
):
    product = create_product(
        tenant=tenant_a,
        code="INUT1",
        description="Item",
        ncm="21069090",
        unit_price_cents=1000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="inut-overlap",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    emit_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    n = inv.number
    with pytest.raises(NfeValidationError, match="conflita"):
        inutilize_number_range(
            tenant=tenant_a,
            provider=provider_sp,
            series=inv.series,
            tp_amb=inv.tp_amb,
            n_ini=n,
            n_fin=n,
            x_just=_JUST,
        )


@pytest.mark.django_db
def test_domain_inutilize_rejects_sefaz(
    nfe_settings, tenant_a, provider_sp
):
    with patch.object(
        StubNfeProvider,
        "inutilizar",
        return_value=NfeEmitResult(
            status="rejected",
            rejection_code="241",
            rejection_message="numero ja inutilizado",
            raw={},
        ),
    ):
        with pytest.raises(NfeValidationError):
            inutilize_number_range(
                tenant=tenant_a,
                provider=provider_sp,
                n_ini=1,
                n_fin=1,
                x_just=_JUST,
            )
    assert NfeInutilization.objects.filter(
        tenant=tenant_a, status=NfeInutilization.Status.REJECTED
    ).exists()


@pytest.mark.django_db
def test_api_inutilize(
    api_client, auth_header, nfe_settings, tenant_a, provider_sp
):
    upsert_number_series(
        tenant=tenant_a, provider=provider_sp, series=1, tp_amb="2", next_number=50
    )
    res = api_client.post(
        reverse("nfe-config-inutilize"),
        {
            "provider_id": str(provider_sp.id),
            "series": 1,
            "tp_amb": "2",
            "n_ini": 50,
            "n_fin": 51,
            "x_just": _JUST,
            "ano": "2026",
        },
        format="json",
        **auth_header,
    )
    assert res.status_code == 201, res.data
    assert res.data["status"] == "accepted"
    assert res.data["n_ini"] == 50
    series = NfeNumberSeries.objects.get(
        tenant=tenant_a, provider=provider_sp, series=1, tp_amb="2"
    )
    assert series.next_number == 52
