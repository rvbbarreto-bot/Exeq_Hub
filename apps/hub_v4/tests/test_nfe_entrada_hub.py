"""Hub V4 — NF-e de entrada (S6)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.master_data.models import Provider, TaxRegime
from apps.nfe.entrada.models import NfeEntradaDocument, NfeEntradaManifestation
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once
from integrations.nfse.tests.pfx_factory import make_test_pfx
from integrations.sefaz_nfe.manifestacao.evento import TP_EVENTO_CIENCIA


@pytest.fixture
def hub_entrada_ctx(db, settings):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    settings.NFE_ENTRADA_STUB_MODE = "138"
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(
        slug="nfe-entrada-hub",
        legal_name="NFe Entrada Hub",
        document="11222333000181",
        settings={"nfe_entrada_enabled": True},
    )
    user = User.objects.create_user(
        email="nfe.entrada@exeq.local", password="Secret123!", name="Entrada Hub"
    )
    TenantMembership.objects.create(
        tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True
    )
    provider = Provider.objects.create(
        tenant=tenant,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        municipal_registration="64021",
        address={"uf": "SP", "municipio": "Atibaia", "codigo_ibge": "3504107"},
    )
    sync_distribuicao_once(tenant=tenant, provider=provider, stub_mode="138")
    doc = NfeEntradaDocument.objects.filter(tenant=tenant).first()
    return {"tenant": tenant, "user": user, "provider": provider, "doc": doc}


def _login(client, ctx):
    return client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": ctx["tenant"].slug,
            "email": ctx["user"].email,
            "password": "Secret123!",
        },
    )


@pytest.mark.django_db
def test_hub_entrada_list_and_nav(client, hub_entrada_ctx):
    _login(client, hub_entrada_ctx)
    r = client.get(reverse("hub-v4-nfe-entrada-list"))
    assert r.status_code == 200
    assert b"NF-e de Entrada" in r.content or b"Captura" in r.content
    assert b"Consultar AN" in r.content
    assert hub_entrada_ctx["doc"].issuer_name.encode() in r.content or b"documento" in r.content.lower()


@pytest.mark.django_db
def test_hub_entrada_detail_and_manifest(client, hub_entrada_ctx):
    _login(client, hub_entrada_ctx)
    doc = hub_entrada_ctx["doc"]
    r = client.get(reverse("hub-v4-nfe-entrada-detail", args=[doc.id]))
    assert r.status_code == 200
    assert b"Manifesta" in r.content

    pfx = make_test_pfx()
    with patch(
        "apps.nfe.entrada.services.manifestacao.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ):
        r = client.post(
            reverse("hub-v4-nfe-entrada-manifest", args=[doc.id]),
            {"tp_evento": TP_EVENTO_CIENCIA},
        )
    assert r.status_code == 302
    doc.refresh_from_db()
    assert doc.manifest_status == NfeEntradaDocument.ManifestStatus.CIENCIA
    assert NfeEntradaManifestation.objects.filter(document=doc).count() == 1


@pytest.mark.django_db
def test_hub_entrada_config(client, hub_entrada_ctx):
    _login(client, hub_entrada_ctx)
    provider = hub_entrada_ctx["provider"]
    r = client.get(
        reverse("hub-v4-nfe-entrada-config"),
        {"provider_id": str(provider.id)},
    )
    assert r.status_code == 200
    r = client.post(
        reverse("hub-v4-nfe-entrada-config"),
        {
            "provider_id": str(provider.id),
            "automatic_enabled": "on",
            "interval_seconds": "3600",
        },
    )
    assert r.status_code == 302
    provider.refresh_from_db()
    cursor = provider.nfe_distribuicao_cursor
    assert cursor.automatic_enabled is True


@pytest.mark.django_db
def test_hub_entrada_sync_certificate_error(client, hub_entrada_ctx):
    from apps.accounts.exceptions import CertificateNotUsableError

    _login(client, hub_entrada_ctx)
    provider = hub_entrada_ctx["provider"]
    with patch(
        "apps.hub_v4.nfe_entrada_views.schedule_distribuicao_sync",
        side_effect=CertificateNotUsableError("Certificado digital expirado"),
    ):
        r = client.post(
            reverse("hub-v4-nfe-entrada-sync"),
            {"provider_id": str(provider.id)},
        )
    assert r.status_code == 302
    assert reverse("hub-v4-nfe-entrada-list") in r.url
    r = client.get(r.url, follow=True)
    assert b"Certificado digital expirado" in r.content
    assert b"Certificados" in r.content


@pytest.mark.django_db
def test_hub_entrada_disabled_redirects(client, db, settings):
    settings.NFE_ENTRADA_ENABLED = False
    roles = {r.code: r for r in ensure_system_roles()}
    tenant = Tenant.objects.create(slug="no-entrada", legal_name="No Entrada", document="11222333000181")
    user = User.objects.create_user(email="no.entrada@exeq.local", password="Secret123!", name="No")
    TenantMembership.objects.create(tenant=tenant, user=user, role=roles["tenant_admin"], is_active=True)
    client.post(
        reverse("hub-v4-login"),
        {"tenant_slug": tenant.slug, "email": user.email, "password": "Secret123!"},
    )
    r = client.get(reverse("hub-v4-nfe-entrada-list"))
    assert r.status_code == 302
    assert reverse("hub-v4-dashboard") in r.url
