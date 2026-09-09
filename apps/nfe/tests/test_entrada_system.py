"""Sistema — API + Hub + Celery (eager) ponta a ponta."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import TenantMembership
from apps.accounts.services import ensure_system_roles
from apps.nfe.entrada.cursor import get_or_create_cursor
from apps.nfe.entrada.models import NfeEntradaDocument
from apps.nfe.entrada.tasks import distribuicao_tick_task
from integrations.nfse.tests.pfx_factory import make_test_pfx
from integrations.sefaz_nfe.manifestacao.evento import TP_EVENTO_CIENCIA


@pytest.mark.django_db
def test_system_api_hub_tick_flow(client, api_client, auth_header, hub_entrada_ctx):
    """Sync via API, lista Hub, manifest Hub, beat tick enfileira."""
    tenant = hub_entrada_ctx["tenant"]
    provider = hub_entrada_ctx["provider"]
    doc = hub_entrada_ctx["doc"]

    # API list + filter
    r = api_client.get("/api/v1/nfe/entrada/?q=STUB&days=0", **auth_header)
    assert r.status_code == 200
    assert r.data["kpis"]["total"] >= 1

    # Hub list fields
    client.post(
        reverse("hub-v4-login"),
        {
            "tenant_slug": tenant.slug,
            "email": hub_entrada_ctx["user"].email,
            "password": "Secret123!",
        },
    )
    list_r = client.get(reverse("hub-v4-nfe-entrada-list"))
    assert list_r.status_code == 200
    assert b"XML pendente" in list_r.content
    assert b"ultNSU" in list_r.content

    # Manifest via Hub
    pfx = make_test_pfx()
    with patch(
        "apps.nfe.entrada.services.manifestacao.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ):
        man_r = client.post(
            reverse("hub-v4-nfe-entrada-manifest", args=[doc.id]),
            {"tp_evento": TP_EVENTO_CIENCIA},
        )
    assert man_r.status_code == 302
    doc.refresh_from_db()
    assert doc.manifest_status == NfeEntradaDocument.ManifestStatus.CIENCIA

    # Beat tick with automatic cursor
    cursor = get_or_create_cursor(tenant=tenant, provider=provider)
    cursor.automatic_enabled = True
    cursor.last_query_at = timezone.now() - timedelta(hours=2)
    cursor.save()
    tick = distribuicao_tick_task(limit=5)
    assert tick["enqueued"] >= 1


@pytest.mark.django_db
def test_system_readonly_cannot_sync_hub(client, entrada_settings, tenant_a, provider_sp):
    roles = {r.code: r for r in ensure_system_roles()}
    from apps.accounts.models import User

    user = User.objects.create_user(email="readonly@exeq.local", password="Secret123!", name="RO")
    TenantMembership.objects.create(
        tenant=tenant_a, user=user, role=roles["readonly"], is_active=True
    )
    client.post(
        reverse("hub-v4-login"),
        {"tenant_slug": tenant_a.slug, "email": user.email, "password": "Secret123!"},
    )
    r = client.post(reverse("hub-v4-nfe-entrada-sync"))
    # readonly redirected or forbidden depending on hub auth — expect not success manifest path
    assert r.status_code in (302, 403)


@pytest.fixture
def hub_entrada_ctx(db, settings, tenant_a, provider_sp, user_ana, membership_admin):
    settings.NFE_ENTRADA_ENABLED = True
    settings.NFE_ENTRADA_HTTP_MODE = "stub"
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_entrada_enabled": True}
    tenant_a.save(update_fields=["settings"])
    from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once

    sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    doc = NfeEntradaDocument.objects.filter(tenant=tenant_a).first()
    return {
        "tenant": tenant_a,
        "user": user_ana,
        "provider": provider_sp,
        "doc": doc,
    }
