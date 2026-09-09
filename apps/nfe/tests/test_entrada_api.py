"""API REST — NF-e de entrada (S6)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.models import NfeEntradaDocument
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once
from integrations.nfse.tests.pfx_factory import make_test_pfx
from integrations.sefaz_nfe.manifestacao.evento import TP_EVENTO_CIENCIA


@pytest.fixture
def entrada_api_ctx(settings, tenant_a, membership_admin):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    settings.NFE_ENTRADA_STUB_MODE = "138"
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_entrada_enabled": True}
    tenant_a.save(update_fields=["settings"])
    provider = Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        address={"uf": "SP", "municipio": "Atibaia", "codigo_ibge": "3504107"},
    )
    sync_distribuicao_once(tenant=tenant_a, provider=provider, stub_mode="138")
    doc = NfeEntradaDocument.objects.filter(tenant=tenant_a).first()
    return {"tenant": tenant_a, "provider": provider, "doc": doc}


@pytest.mark.django_db
def test_api_entrada_list_and_detail(api_client, auth_header, entrada_api_ctx):
    doc = entrada_api_ctx["doc"]
    assert doc is not None
    r = api_client.get("/api/v1/nfe/entrada/?days=0", **auth_header)
    assert r.status_code == 200
    assert r.data["count"] >= 1
    assert "kpis" in r.data

    r = api_client.get(f"/api/v1/nfe/entrada/{doc.id}/", **auth_header)
    assert r.status_code == 200
    assert r.data["access_key"] == doc.access_key


@pytest.mark.django_db
def test_api_entrada_sync(api_client, auth_header, entrada_api_ctx):
    provider = entrada_api_ctx["provider"]
    r = api_client.post(
        "/api/v1/nfe/entrada/sync/",
        {"provider_id": str(provider.id)},
        format="json",
        **auth_header,
    )
    assert r.status_code == 202
    assert r.data["provider_id"] == str(provider.id)


@pytest.mark.django_db
def test_api_entrada_distribution_config(api_client, auth_header, entrada_api_ctx):
    provider = entrada_api_ctx["provider"]
    r = api_client.get(
        f"/api/v1/nfe/entrada/distribution/status/?provider_id={provider.id}",
        **auth_header,
    )
    assert r.status_code == 200
    assert r.data["cnpj"]

    r = api_client.put(
        "/api/v1/nfe/entrada/distribution/config/",
        {
            "provider_id": str(provider.id),
            "automatic_enabled": True,
            "interval_seconds": 7200,
        },
        format="json",
        **auth_header,
    )
    assert r.status_code == 200
    assert r.data["automatic_enabled"] is True
    assert r.data["interval_seconds"] == 7200


@pytest.mark.django_db
def test_api_entrada_manifest(api_client, auth_header, entrada_api_ctx):
    doc = entrada_api_ctx["doc"]
    pfx = make_test_pfx()
    with patch(
        "apps.nfe.entrada.services.manifestacao.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ):
        r = api_client.post(
            f"/api/v1/nfe/entrada/{doc.id}/manifest/",
            {"tp_evento": TP_EVENTO_CIENCIA},
            format="json",
            **auth_header,
        )
    assert r.status_code == 201
    assert r.data["success"] is True
    doc.refresh_from_db()
    assert doc.manifest_status == NfeEntradaDocument.ManifestStatus.CIENCIA


@pytest.mark.django_db
def test_api_entrada_disabled_returns_403(api_client, auth_header, tenant_a, membership_admin):
    r = api_client.get("/api/v1/nfe/entrada/?days=0", **auth_header)
    assert r.status_code == 403


@pytest.mark.django_db
def test_api_entrada_list_filters(api_client, auth_header, entrada_api_ctx):
    doc = entrada_api_ctx["doc"]
    r = api_client.get(
        f"/api/v1/nfe/entrada/?manifest_status=none&xml_status=pending&days=0",
        **auth_header,
    )
    assert r.status_code == 200
    assert r.data["count"] >= 1
    assert r.data["results"][0]["id"] == str(doc.id)


@pytest.mark.django_db
def test_api_entrada_manifest_idempotent(api_client, auth_header, entrada_api_ctx):
    doc = entrada_api_ctx["doc"]
    pfx = make_test_pfx()
    with patch(
        "apps.nfe.entrada.services.manifestacao.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ):
        first = api_client.post(
            f"/api/v1/nfe/entrada/{doc.id}/manifest/",
            {"tp_evento": TP_EVENTO_CIENCIA},
            format="json",
            **auth_header,
        )
        second = api_client.post(
            f"/api/v1/nfe/entrada/{doc.id}/manifest/",
            {"tp_evento": TP_EVENTO_CIENCIA},
            format="json",
            **auth_header,
        )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["idempotent"] is True


@pytest.mark.django_db
def test_api_entrada_sync_no_provider_400(api_client, auth_header, entrada_settings, tenant_a):
    r = api_client.post("/api/v1/nfe/entrada/sync/", {}, format="json", **auth_header)
    assert r.status_code == 400
    assert r.data["code"] == "nfe_entrada_provider"


@pytest.mark.django_db
def test_api_entrada_distribution_status_no_provider(api_client, auth_header, entrada_settings, tenant_a):
    r = api_client.get("/api/v1/nfe/entrada/distribution/status/", **auth_header)
    assert r.status_code == 200
    assert r.data == {"cursors": []}


@pytest.mark.django_db
def test_api_entrada_tenant_isolation(api_client, entrada_api_ctx, tenant_b):
    from apps.accounts.models import TenantMembership, User
    from apps.accounts.services import ensure_system_roles

    roles = {r.code: r for r in ensure_system_roles()}
    user_b = User.objects.create_user(email="b@exeq.local", password="Secret123!", name="B")
    TenantMembership.objects.create(tenant=tenant_b, user=user_b, role=roles["tenant_admin"])
    login_b = api_client.post(
        "/api/v1/auth/login",
        {"tenant_slug": tenant_b.slug, "email": user_b.email, "password": "Secret123!"},
        format="json",
    )
    header_b = {"HTTP_AUTHORIZATION": f"Bearer {login_b.data['access']}"}
    doc = entrada_api_ctx["doc"]
    r = api_client.get(f"/api/v1/nfe/entrada/{doc.id}/", **header_b)
    assert r.status_code == 404
