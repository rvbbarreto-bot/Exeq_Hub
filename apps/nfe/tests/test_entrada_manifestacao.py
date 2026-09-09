"""Manifestação NF-e entrada — ciência e gates."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.exceptions import ManifestationError
from apps.nfe.entrada.models import NfeEntradaDocument, NfeEntradaManifestation
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once
from apps.nfe.entrada.services.manifestacao import manifest_entrada_document
from integrations.nfse.tests.pfx_factory import make_test_pfx
from integrations.sefaz_nfe.manifestacao.evento import (
    TP_EVENTO_CIENCIA,
    TP_EVENTO_CONFIRMACAO,
    TP_EVENTO_NAO_REALIZADA,
)

STUB_KEY = "35260111222333000181550010000000011234567890"


@pytest.fixture
def entrada_settings(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    settings.NFE_ENTRADA_STUB_MODE = "138"
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_entrada_enabled": True}
    tenant_a.save(update_fields=["settings"])
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        address={"uf": "SP", "municipio": "Atibaia", "codigo_ibge": "3504107"},
    )


@pytest.fixture
def entrada_doc(entrada_settings, tenant_a, provider_sp):
    sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    return NfeEntradaDocument.objects.filter(tenant=tenant_a).order_by("nsu").first()


@pytest.fixture
def pfx_mock():
    pfx = make_test_pfx()
    with patch(
        "apps.nfe.entrada.services.manifestacao.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ):
        yield


@pytest.mark.django_db
def test_ciencia_accepted(entrada_doc, pfx_mock):
    result = manifest_entrada_document(
        document=entrada_doc,
        tp_evento=TP_EVENTO_CIENCIA,
    )
    assert result.success is True
    assert result.protocol
    assert result.manifestation.status == NfeEntradaManifestation.Status.ACCEPTED

    entrada_doc.refresh_from_db()
    assert entrada_doc.manifest_status == NfeEntradaDocument.ManifestStatus.CIENCIA
    assert entrada_doc.manifestations.count() == 1
    assert entrada_doc.manifestations.first().stored_file_id is not None


@pytest.mark.django_db
def test_ciencia_idempotent(entrada_doc, pfx_mock):
    first = manifest_entrada_document(document=entrada_doc, tp_evento=TP_EVENTO_CIENCIA)
    second = manifest_entrada_document(document=entrada_doc, tp_evento=TP_EVENTO_CIENCIA)
    assert first.idempotent is False
    assert second.idempotent is True
    assert NfeEntradaManifestation.objects.filter(document=entrada_doc).count() == 1


@pytest.mark.django_db
def test_confirmacao_requires_confirmed(entrada_doc, pfx_mock):
    with pytest.raises(ManifestationError, match="Confirmação explícita"):
        manifest_entrada_document(
            document=entrada_doc,
            tp_evento=TP_EVENTO_CONFIRMACAO,
            confirmed=False,
        )


@pytest.mark.django_db
def test_confirmacao_explicit(entrada_doc, pfx_mock):
    result = manifest_entrada_document(
        document=entrada_doc,
        tp_evento=TP_EVENTO_CONFIRMACAO,
        confirmed=True,
    )
    assert result.success is True
    entrada_doc.refresh_from_db()
    assert entrada_doc.manifest_status == NfeEntradaDocument.ManifestStatus.CONFIRMADA


@pytest.mark.django_db
def test_nao_realizada_requires_justificativa(entrada_doc, pfx_mock):
    with pytest.raises(ManifestationError):
        manifest_entrada_document(
            document=entrada_doc,
            tp_evento=TP_EVENTO_NAO_REALIZADA,
            confirmed=True,
            justificativa="curta",
        )


@pytest.mark.django_db
def test_ciencia_schedules_sync(entrada_doc, pfx_mock):
    with patch("apps.nfe.entrada.services.manifestacao.schedule_distribuicao_sync") as sched:
        manifest_entrada_document(document=entrada_doc, tp_evento=TP_EVENTO_CIENCIA)
    sched.assert_called_once()


@pytest.mark.django_db
def test_invalid_tp_evento_raises(entrada_doc, pfx_mock):
    with pytest.raises(ManifestationError, match="tpEvento inválido"):
        manifest_entrada_document(document=entrada_doc, tp_evento="999999")


@pytest.mark.django_db
def test_desconhecimento_explicit(entrada_doc, pfx_mock):
    from integrations.sefaz_nfe.manifestacao.evento import TP_EVENTO_DESCONHECIMENTO

    result = manifest_entrada_document(
        document=entrada_doc,
        tp_evento=TP_EVENTO_DESCONHECIMENTO,
        confirmed=True,
    )
    assert result.success is True
    entrada_doc.refresh_from_db()
    assert entrada_doc.manifest_status == NfeEntradaDocument.ManifestStatus.DESCONHECIDA


@pytest.mark.django_db
def test_manifest_tenant_isolation(entrada_settings, tenant_a, tenant_b, provider_sp, pfx_mock):
    provider_b = Provider.objects.create(
        tenant=tenant_b,
        document="11222333000181",
        legal_name="BETA LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="99999",
        address={"uf": "SP"},
    )
    tenant_b.settings = {"nfe_entrada_enabled": True}
    tenant_b.save(update_fields=["settings"])

    sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    doc_a = NfeEntradaDocument.objects.filter(tenant=tenant_a).first()
    manifest_entrada_document(document=doc_a, tp_evento=TP_EVENTO_CIENCIA)

    doc_b = NfeEntradaDocument.objects.create(
        tenant=tenant_b,
        provider=provider_b,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key=STUB_KEY,
        recipient_cnpj="11222333000181",
    )
    with patch(
        "apps.nfe.entrada.services.manifestacao.load_primary_pfx_material",
        return_value=(make_test_pfx(), "test"),
    ):
        manifest_entrada_document(document=doc_b, tp_evento=TP_EVENTO_CIENCIA)

    assert NfeEntradaManifestation.objects.filter(tenant=tenant_a).count() == 1
    assert NfeEntradaManifestation.objects.filter(tenant=tenant_b).count() == 1
