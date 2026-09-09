"""HTTP NFeDistribuicaoDFe — transport, parse SOAP, provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.exceptions import DistributionError
from apps.nfe.entrada.models import NfeEntradaDocument
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once
from integrations.sefaz_nfe.distribuicao import (
    HttpNfeDistribuicaoProvider,
    build_dist_dfe_interesse,
    parse_ret_dist_dfe_response,
)
from integrations.sefaz_nfe.distribuicao.transport import DistribuicaoHttpResponse
from integrations.sefaz_nfe.tests.distribuicao_soap_fixtures import (
    soap_137,
    soap_138_one_doc,
    soap_656,
)
from integrations.nfse.tests.pfx_factory import make_test_pfx

STUB_KEY = "35260111222333000181550010000000011234567890"


def test_build_dist_dfe_interesse():
    xml = build_dist_dfe_interesse(
        tp_amb="2",
        cnpj="37229907000137",
        ult_nsu="0",
        cuf_autor="35",
    )
    assert "<distDFeInt" in xml
    assert "<CNPJ>37229907000137</CNPJ>" in xml
    assert "<ultNSU>000000000000000</ultNSU>" in xml
    assert "<cUFAutor>35</cUFAutor>" in xml


def test_parse_ret_137():
    parsed = parse_ret_dist_dfe_response(soap_137())
    assert parsed.c_stat == "137"
    assert parsed.documents == ()
    assert parsed.ult_nsu == "000000000000002"


def test_parse_ret_138_with_doczip():
    parsed = parse_ret_dist_dfe_response(soap_138_one_doc(access_key=STUB_KEY))
    assert parsed.c_stat == "138"
    assert len(parsed.documents) == 1
    assert parsed.documents[0].schema_type == "resNFe"
    assert parsed.documents[0].nsu == "000000000000001"


def test_parse_ret_656():
    parsed = parse_ret_dist_dfe_response(soap_656())
    assert parsed.c_stat == "656"


@pytest.fixture
def tenant_entrada(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "http"
    settings.NFE_ENTRADA_HTTP_DRY_RUN = False
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_entrada_enabled": True}
    tenant_a.save(update_fields=["settings"])
    return tenant_a


@pytest.fixture
def provider_sp(tenant_entrada):
    return Provider.objects.create(
        tenant=tenant_entrada,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        address={"uf": "SP", "municipio": "Atibaia", "codigo_ibge": "3504107"},
    )


@pytest.mark.django_db
def test_http_provider_138(tenant_entrada, provider_sp):
    provider = HttpNfeDistribuicaoProvider()
    session = MagicMock()
    session.post.return_value = MagicMock(
        status_code=200,
        text=soap_138_one_doc(access_key=STUB_KEY),
    )
    pfx = make_test_pfx()

    with patch(
        "apps.accounts.certificates.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ):
        result = provider.consultar_dist_nsu(
            cnpj=provider_sp.document,
            ult_nsu="0",
            tp_amb="2",
            context={
                "tenant": tenant_entrada,
                "provider": provider_sp,
                "http_session": session,
            },
        )

    assert result.c_stat == "138"
    assert len(result.documents) == 1
    assert b"resNFe" in result.documents[0].xml_bytes
    session.post.assert_called_once()


@pytest.mark.django_db
def test_http_provider_dry_run(settings, tenant_entrada, provider_sp):
    settings.NFE_ENTRADA_HTTP_DRY_RUN = True
    provider = HttpNfeDistribuicaoProvider()
    with patch(
        "apps.accounts.certificates.load_primary_pfx_material",
    ) as load_mock:
        result = provider.consultar_dist_nsu(
            cnpj=provider_sp.document,
            ult_nsu="0",
            context={"tenant": tenant_entrada, "provider": provider_sp},
        )
    load_mock.assert_not_called()
    assert result.c_stat == "137"
    assert result.raw.get("dry_run") is True


@pytest.mark.django_db
def test_http_provider_http_500_raises(tenant_entrada, provider_sp):
    provider = HttpNfeDistribuicaoProvider()
    session = MagicMock()
    session.post.return_value = MagicMock(status_code=503, text="unavailable")
    pfx = make_test_pfx()

    with patch(
        "apps.accounts.certificates.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ):
        with pytest.raises(DistributionError, match="503"):
            provider.consultar_dist_nsu(
                cnpj=provider_sp.document,
                ult_nsu="0",
                context={
                    "tenant": tenant_entrada,
                    "provider": provider_sp,
                    "http_session": session,
                },
            )


@pytest.mark.django_db
def test_sync_with_http_provider_mock(tenant_entrada, provider_sp):
    pfx = make_test_pfx()
    responses = [
        DistribuicaoHttpResponse(http_status=200, body=soap_138_one_doc(access_key=STUB_KEY)),
        DistribuicaoHttpResponse(http_status=200, body=soap_137(ult_nsu="000000000000001")),
    ]

    def _fake_post(**kwargs):
        return responses.pop(0)

    with patch(
        "apps.accounts.certificates.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ), patch(
        "integrations.sefaz_nfe.distribuicao.transport.post_nfe_distribuicao",
        side_effect=_fake_post,
    ):
        result = sync_distribuicao_once(tenant=tenant_entrada, provider=provider_sp)

    assert result.success is True
    assert result.documents_created == 1
    assert NfeEntradaDocument.objects.filter(tenant=tenant_entrada).count() == 1
    doc = NfeEntradaDocument.objects.get(tenant=tenant_entrada)
    assert doc.access_key == STUB_KEY
