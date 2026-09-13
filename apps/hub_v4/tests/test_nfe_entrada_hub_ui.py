"""Hub V4 — telas e campos NF-e de entrada (UI smoke estrutural)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.nfe.entrada.models import NfeEntradaDocument, NfeEntradaManifestation


def _u(text: str) -> bytes:
    return text.encode("utf-8")


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
class TestNfeEntradaListUI:
    LIST_FIELDS = (
        'id="q"',
        'id="manifest_status"',
        'id="xml_status"',
        "XML pendente",
        "Sem manifesta",
        "ultNSU",
        "maxNSU",
        "Consultar AN",
        "Configura",
        "Emitente",
        "Manifesta",
    )

    def test_list_renders_kpis_filters_cursor_table(self, client, hub_entrada_ctx):
        _login(client, hub_entrada_ctx)
        r = client.get(reverse("hub-v4-nfe-entrada-list"))
        assert r.status_code == 200
        for marker in self.LIST_FIELDS:
            assert _u(marker) in r.content, f"missing {marker!r}"

    def test_list_filter_manifest_status(self, client, hub_entrada_ctx):
        _login(client, hub_entrada_ctx)
        r = client.get(
            reverse("hub-v4-nfe-entrada-list"),
            {"manifest_status": "none", "xml_status": "all"},
        )
        assert r.status_code == 200
        assert b'name="manifest_status"' in r.content
        assert b'value="none"' in r.content

    def test_list_search_query_preserved(self, client, hub_entrada_ctx):
        _login(client, hub_entrada_ctx)
        doc = hub_entrada_ctx["doc"]
        term = doc.issuer_name[:8]
        r = client.get(reverse("hub-v4-nfe-entrada-list"), {"q": term, "days": "0"})
        assert r.status_code == 200
        assert term.encode() in r.content


@pytest.mark.django_db
class TestNfeEntradaDetailUI:
    DETAIL_FIELDS = (
        "Chave de acesso",
        "CNPJ emitente",
        "CNPJ destinat",
        "Manifesta",
        "Histórico de manifest",
        "Ciência da emissão",
        "Confirmar operação",
        "Desconhecimento",
        "justificativa",
        "Lista",
    )

    def test_detail_renders_summary_and_manifest_actions(self, client, hub_entrada_ctx):
        _login(client, hub_entrada_ctx)
        doc = hub_entrada_ctx["doc"]
        r = client.get(reverse("hub-v4-nfe-entrada-detail", args=[doc.id]))
        assert r.status_code == 200
        assert doc.access_key.encode() in r.content
        for marker in self.DETAIL_FIELDS:
            assert _u(marker) in r.content, f"missing {marker!r}"

    def test_detail_hides_ciencia_after_accepted(self, client, hub_entrada_ctx):
        _login(client, hub_entrada_ctx)
        doc = hub_entrada_ctx["doc"]
        doc.manifest_status = NfeEntradaDocument.ManifestStatus.CIENCIA
        doc.save(update_fields=["manifest_status"])
        NfeEntradaManifestation.objects.create(
            tenant=hub_entrada_ctx["tenant"],
            document=doc,
            tp_evento=NfeEntradaManifestation.EventType.CIENCIA,
            status=NfeEntradaManifestation.Status.ACCEPTED,
            protocol="135000000000001",
        )
        r = client.get(reverse("hub-v4-nfe-entrada-detail", args=[doc.id]))
        assert _u("Ciência da emissão") not in r.content
        assert _u("Histórico de manifest") in r.content


@pytest.mark.django_db
class TestNfeEntradaConfigUI:
    CONFIG_FIELDS = (
        "Distribuição automática",
        "automatic_enabled",
        "interval_seconds",
        "ultNSU",
        "Salvar",
    )

    def test_config_renders_form_fields(self, client, hub_entrada_ctx):
        _login(client, hub_entrada_ctx)
        provider = hub_entrada_ctx["provider"]
        r = client.get(
            reverse("hub-v4-nfe-entrada-config"),
            {"provider_id": str(provider.id)},
        )
        assert r.status_code == 200
        for marker in self.CONFIG_FIELDS:
            assert _u(marker) in r.content, f"missing {marker!r}"


@pytest.mark.django_db
def test_hub_sidebar_shows_entrada_when_enabled(client, hub_entrada_ctx):
    _login(client, hub_entrada_ctx)
    r = client.get(reverse("hub-v4-nfe-entrada-list"))
    assert _u("NF-e de Entrada") in r.content or b"entrada" in r.content.lower()


@pytest.mark.django_db
def test_readonly_hides_write_actions(client, entrada_settings, tenant_a, provider_sp):
    roles = {r.code: r for r in ensure_system_roles()}
    user = User.objects.create_user(email="ro.ui@exeq.local", password="Secret123!", name="RO UI")
    TenantMembership.objects.create(
        tenant=tenant_a, user=user, role=roles["readonly"], is_active=True
    )
    tenant_a.settings = {**(tenant_a.settings or {}), "nfe_entrada_enabled": True}
    tenant_a.save(update_fields=["settings"])
    client.post(
        reverse("hub-v4-login"),
        {"tenant_slug": tenant_a.slug, "email": user.email, "password": "Secret123!"},
    )
    r = client.get(reverse("hub-v4-nfe-entrada-list"))
    assert r.status_code == 200
    assert _u("Consultar AN") not in r.content
