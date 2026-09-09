"""NfeDistribuicaoService — distNSU stub, NSU, idempotência."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.exceptions import NfeEntradaDisabledError
from apps.nfe.entrada.models import NfeDistribuicaoCursor, NfeEntradaDocument, NfeDistribuicaoSyncLog
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once
from integrations.sefaz_nfe.distribuicao import CSTAT_CONSUMO_INDEVIDO, CSTAT_NENHUM_DOCUMENTO


@pytest.fixture
def entrada_settings(settings, tenant_a):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    settings.NFE_ENTRADA_STUB_MODE = "138"
    settings.NFE_ENTRADA_BLOCK_656_SECONDS = 3600
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
def provider_beta(tenant_b):
    return Provider.objects.create(
        tenant=tenant_b,
        document="11222333000181",
        legal_name="BETA LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="99999",
        address={"uf": "SP", "municipio": "São Paulo", "codigo_ibge": "3550308"},
    )


@pytest.mark.django_db
def test_sync_disabled_raises(tenant_a, provider_sp, settings):
    settings.NFE_ENTRADA_ENABLED = False
    with pytest.raises(NfeEntradaDisabledError):
        sync_distribuicao_once(tenant=tenant_a, provider=provider_sp)


@pytest.mark.django_db
def test_sync_138_creates_documents_and_advances_nsu(entrada_settings, tenant_a, provider_sp):
    result = sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    assert result.success is True
    assert result.documents_created == 2
    assert result.documents_processed == 2
    assert result.ult_nsu_after == "000000000000002"

    cursor = NfeDistribuicaoCursor.objects.get(tenant=tenant_a, provider=provider_sp)
    assert cursor.ult_nsu == "000000000000002"
    assert cursor.last_c_stat == "138"

    docs = NfeEntradaDocument.objects.filter(tenant=tenant_a, provider=provider_sp)
    assert docs.count() == 2
    assert all(d.schema_type == NfeEntradaDocument.SchemaType.RES_NFE for d in docs)
    assert all(d.xml_status == NfeEntradaDocument.XmlStatus.PENDING for d in docs)
    assert docs.filter(access_key="").count() == 0

    log = NfeDistribuicaoSyncLog.objects.filter(tenant=tenant_a).first()
    assert log is not None
    assert log.success is True
    assert log.documents_count == 2


@pytest.mark.django_db
def test_sync_137_after_exhausted(entrada_settings, tenant_a, provider_sp):
    sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    result = sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    assert result.c_stat == CSTAT_NENHUM_DOCUMENTO
    assert result.documents_created == 0
    assert NfeEntradaDocument.objects.filter(tenant=tenant_a).count() == 2


@pytest.mark.django_db
def test_sync_idempotent_no_duplicates(entrada_settings, tenant_a, provider_sp):
    sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    cursor = NfeDistribuicaoCursor.objects.get(tenant=tenant_a, provider=provider_sp)
    cursor.ult_nsu = "0"
    cursor.save(update_fields=["ult_nsu", "updated_at"])

    result = sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    assert result.documents_created == 0
    assert result.documents_processed == 2
    assert NfeEntradaDocument.objects.filter(tenant=tenant_a).count() == 2


@pytest.mark.django_db
def test_sync_656_blocks_cursor(entrada_settings, tenant_a, provider_sp):
    result = sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="656")
    assert result.blocked is True
    assert result.c_stat == CSTAT_CONSUMO_INDEVIDO
    assert result.documents_created == 0

    cursor = NfeDistribuicaoCursor.objects.get(tenant=tenant_a, provider=provider_sp)
    assert cursor.blocked_until is not None
    assert cursor.blocked_until > timezone.now()

    blocked = sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    assert blocked.blocked is True
    assert blocked.documents_created == 0


@pytest.mark.django_db
def test_sync_tenant_isolation(entrada_settings, tenant_a, tenant_b, provider_sp, provider_beta):
    tenant_b.settings = {**(tenant_b.settings or {}), "nfe_entrada_enabled": True}
    tenant_b.save(update_fields=["settings"])
    sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    sync_distribuicao_once(tenant=tenant_b, provider=provider_beta, stub_mode="138")

    assert NfeEntradaDocument.objects.filter(tenant=tenant_a).count() == 2
    assert NfeEntradaDocument.objects.filter(tenant=tenant_b).count() == 2
    keys_a = set(NfeEntradaDocument.objects.filter(tenant=tenant_a).values_list("access_key", flat=True))
    keys_b = set(NfeEntradaDocument.objects.filter(tenant=tenant_b).values_list("access_key", flat=True))
    assert keys_a.isdisjoint(keys_b)


@pytest.mark.django_db
def test_sync_137_direct(entrada_settings, tenant_a, provider_sp):
    result = sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="137")
    assert result.c_stat == CSTAT_NENHUM_DOCUMENTO
    assert result.documents_created == 0
    cursor = NfeDistribuicaoCursor.objects.get(tenant=tenant_a, provider=provider_sp)
    assert cursor.ult_nsu == "000000000000000"
