"""Testes de models NF-e de entrada — constraints e isolamento."""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.models import (
    NfeDistribuicaoCursor,
    NfeEntradaDocument,
    NfeEntradaManifestation,
)

STUB_KEY_1 = "35260111222333000181550010000000011234567890"
STUB_KEY_2 = "35260111222333000181550010000000021234567890"


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
def provider_beta(tenant_b):
    return Provider.objects.create(
        tenant=tenant_b,
        document="11222333000181",
        legal_name="BETA FORN LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="12345",
        address={"uf": "SP", "municipio": "São Paulo", "codigo_ibge": "3550308"},
    )


@pytest.mark.django_db
def test_cursor_one_per_provider(tenant_a, provider_sp):
    NfeDistribuicaoCursor.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        cnpj=provider_sp.document,
    )
    with pytest.raises(IntegrityError):
        NfeDistribuicaoCursor.objects.create(
            tenant=tenant_a,
            provider=provider_sp,
            cnpj=provider_sp.document,
        )


@pytest.mark.django_db
def test_document_unique_access_key_per_tenant(tenant_a, provider_sp):
    key = STUB_KEY_1
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key=key,
    )
    with pytest.raises(IntegrityError):
        NfeEntradaDocument.objects.create(
            tenant=tenant_a,
            provider=provider_sp,
            nsu="000000000000002",
            schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
            access_key=key,
        )


@pytest.mark.django_db
def test_document_unique_nsu_per_provider(tenant_a, provider_sp):
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key=STUB_KEY_1,
    )
    with pytest.raises(IntegrityError):
        NfeEntradaDocument.objects.create(
            tenant=tenant_a,
            provider=provider_sp,
            nsu="000000000000001",
            schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
            access_key=STUB_KEY_2,
        )


@pytest.mark.django_db
def test_same_access_key_allowed_across_tenants(
    tenant_a, tenant_b, provider_sp, provider_beta
):
    key = STUB_KEY_1
    NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key=key,
    )
    doc_b = NfeEntradaDocument.objects.create(
        tenant=tenant_b,
        provider=provider_beta,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key=key,
    )
    assert doc_b.tenant_id == tenant_b.id


@pytest.mark.django_db
def test_manifestation_unique_accepted_per_event(tenant_a, provider_sp):
    doc = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key=STUB_KEY_1,
    )
    NfeEntradaManifestation.objects.create(
        tenant=tenant_a,
        document=doc,
        tp_evento=NfeEntradaManifestation.EventType.CIENCIA,
        n_seq=1,
        status=NfeEntradaManifestation.Status.ACCEPTED,
        protocol="135000000000001",
    )
    with pytest.raises(IntegrityError):
        NfeEntradaManifestation.objects.create(
            tenant=tenant_a,
            document=doc,
            tp_evento=NfeEntradaManifestation.EventType.CIENCIA,
            n_seq=1,
            status=NfeEntradaManifestation.Status.ACCEPTED,
            protocol="135000000000002",
        )


@pytest.mark.django_db
def test_manifestation_rejected_not_unique_blocked(tenant_a, provider_sp):
    doc = NfeEntradaDocument.objects.create(
        tenant=tenant_a,
        provider=provider_sp,
        nsu="000000000000001",
        schema_type=NfeEntradaDocument.SchemaType.RES_NFE,
        access_key=STUB_KEY_1,
    )
    NfeEntradaManifestation.objects.create(
        tenant=tenant_a,
        document=doc,
        tp_evento=NfeEntradaManifestation.EventType.CIENCIA,
        n_seq=1,
        status=NfeEntradaManifestation.Status.REJECTED,
    )
    second = NfeEntradaManifestation.objects.create(
        tenant=tenant_a,
        document=doc,
        tp_evento=NfeEntradaManifestation.EventType.CIENCIA,
        n_seq=1,
        status=NfeEntradaManifestation.Status.REJECTED,
    )
    assert second.id
