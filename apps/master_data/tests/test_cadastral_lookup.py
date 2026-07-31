from datetime import timedelta

import pytest
from django.utils import timezone

from apps.master_data.models import DataSource, Provider
from apps.master_data.services import create_provider, lookup_document
from integrations.cadastro.exceptions import (
    CadastroCpfLookupNotSupportedError,
    CadastroDocumentInvalidError,
    CadastroNotFoundError,
)
from integrations.cadastro.stub import STUB_CNPJ_MISSING, STUB_CNPJ_OK


@pytest.mark.django_db
def test_lookup_provider_success_api(api_client, auth_header, tenant_a, settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    res = api_client.post(
        "/api/v1/master-data/providers/lookup-document",
        {"document": STUB_CNPJ_OK},
        format="json",
        **auth_header,
    )
    assert res.status_code == 200, res.data
    assert res.data["legal_name"]
    assert res.data["address"]["uf"] == "SP"
    assert Provider.objects.filter(tenant=tenant_a).count() == 0


@pytest.mark.django_db
def test_lookup_customer_alias_on_viewset(api_client, auth_header, settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    res = api_client.post(
        "/api/v1/customers/lookup-document/",
        {"document": STUB_CNPJ_OK},
        format="json",
        **auth_header,
    )
    assert res.status_code == 200
    assert res.data["document"] == STUB_CNPJ_OK


@pytest.mark.django_db
def test_lookup_invalid_cnpj(api_client, auth_header):
    res = api_client.post(
        "/api/v1/master-data/providers/lookup-document",
        {"document": "123"},
        format="json",
        **auth_header,
    )
    assert res.status_code == 400
    assert res.data["code"] == "cadastro_document_invalid"


@pytest.mark.django_db
def test_lookup_cpf_rejected(api_client, auth_header):
    res = api_client.post(
        "/api/v1/master-data/customers/lookup-document",
        {"document": "52998224725"},
        format="json",
        **auth_header,
    )
    assert res.status_code == 400
    assert res.data["code"] == "cadastro_cpf_lookup_not_supported"


@pytest.mark.django_db
def test_lookup_not_found(api_client, auth_header, settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    res = api_client.post(
        "/api/v1/master-data/providers/lookup-document",
        {"document": STUB_CNPJ_MISSING},
        format="json",
        **auth_header,
    )
    assert res.status_code == 404
    assert res.data["code"] == "cadastro_not_found"


@pytest.mark.django_db
def test_lookup_provider_unavailable(api_client, auth_header, monkeypatch, settings):
    settings.CADASTRO_HTTP_MODE = "stub"

    def boom(*, cnpj):
        from integrations.cadastro.exceptions import CadastroProviderUnavailableError

        raise CadastroProviderUnavailableError("fora do ar")

    monkeypatch.setattr(
        "apps.master_data.services.get_cadastro_gateway",
        lambda: type("G", (), {"lookup_cnpj": staticmethod(boom)})(),
    )
    res = api_client.post(
        "/api/v1/master-data/providers/lookup-document",
        {"document": STUB_CNPJ_OK},
        format="json",
        **auth_header,
    )
    assert res.status_code == 503
    assert res.data["code"] == "cadastro_provider_unavailable"


@pytest.mark.django_db
def test_cache_within_24h(tenant_a, settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    first = lookup_document(
        tenant=tenant_a, document=STUB_CNPJ_OK, entity_kind="provider"
    )
    provider = create_provider(
        tenant=tenant_a,
        document=STUB_CNPJ_OK,
        legal_name=first.legal_name,
        tax_regime="simples_nacional",
        situacao_cadastral=first.situacao_cadastral,
        data_abertura=first.data_abertura,
        cnae_principal=first.cnae_principal,
        natureza_juridica=first.natureza_juridica,
        porte=first.porte,
        address=first.address.as_dict(),
        data_source=DataSource.RECEITA,
        receita_raw_payload=first.raw,
        last_lookup_at=timezone.now(),
    )
    cached = lookup_document(
        tenant=tenant_a, document=STUB_CNPJ_OK, entity_kind="provider"
    )
    assert cached.cached is True
    assert cached.legal_name == provider.legal_name

    provider.last_lookup_at = timezone.now() - timedelta(hours=25)
    provider.save(update_fields=["last_lookup_at"])
    fresh = lookup_document(
        tenant=tenant_a, document=STUB_CNPJ_OK, entity_kind="provider", force=True
    )
    assert fresh.cached is False


@pytest.mark.django_db
def test_reconsulta_persists_last_lookup(tenant_a, settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    provider = create_provider(
        tenant=tenant_a,
        document=STUB_CNPJ_OK,
        legal_name="Antigo",
        tax_regime="simples_nacional",
    )
    assert provider.last_lookup_at is None
    lookup_document(
        tenant=tenant_a,
        document=STUB_CNPJ_OK,
        entity_kind="provider",
        force=True,
        persist_on_existing=True,
    )
    provider.refresh_from_db()
    assert provider.last_lookup_at is not None
    assert provider.data_source == DataSource.RECEITA
    assert provider.receita_raw_payload
    assert provider.legal_name != "Antigo"


@pytest.mark.django_db
def test_service_rejects_cpf_and_invalid():
    with pytest.raises(CadastroCpfLookupNotSupportedError):
        lookup_document(tenant=None, document="52998224725", entity_kind="customer")
    with pytest.raises(CadastroDocumentInvalidError):
        lookup_document(tenant=None, document="111", entity_kind="provider")


@pytest.mark.django_db
def test_create_provider_with_cadastral_fields_api(api_client, auth_header, settings):
    settings.CADASTRO_HTTP_MODE = "stub"
    looked = api_client.post(
        "/api/v1/master-data/providers/lookup-document",
        {"document": STUB_CNPJ_OK},
        format="json",
        **auth_header,
    ).data
    created = api_client.post(
        "/api/v1/providers/",
        {
            "document": looked["document"],
            "legal_name": looked["legal_name"],
            "tax_regime": "simples_nacional",
            "trade_name": looked["trade_name"],
            "address": looked["address"],
            "situacao_cadastral": looked["situacao_cadastral"],
            "cnae_principal": looked["cnae_principal"],
            "natureza_juridica": looked["natureza_juridica"],
            "porte": looked["porte"],
            "data_source": "receita_federal",
            "receita_raw_payload": looked["raw"],
            "whatsapp": "11999990000",
            "contato_nome": "Renata",
        },
        format="json",
        **auth_header,
    )
    assert created.status_code == 201, created.data
    assert created.data["data_source"] == "receita_federal"
    assert created.data["whatsapp"] == "11999990000"


@pytest.mark.django_db
def test_http_mode_skips_stub_cache(tenant_a, settings):
    settings.CADASTRO_HTTP_MODE = "http"
    provider = create_provider(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EMPRESA STUB 000137 LTDA",
        tax_regime="simples_nacional",
        data_source=DataSource.RECEITA,
        receita_raw_payload={
            "provider": "cadastro_stub",
            "mode": "stub",
            "cnpj": "37229907000137",
            "razao_social": "EMPRESA STUB 000137 LTDA",
        },
        last_lookup_at=timezone.now(),
    )
    from apps.master_data.services import _find_cached

    assert _find_cached(
        tenant=tenant_a, document=provider.document, entity_kind="provider"
    ) is None
