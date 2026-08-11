import pytest

from integrations.evolution.client import EvolutionHttpGateway, EvolutionStubGateway
from integrations.meta_cloud.client import (
    MetaCloudHttpGateway,
    MetaCloudStubGateway,
    get_meta_cloud_gateway,
)
from integrations.whatsapp.gateway import (
    get_whatsapp_gateway,
    resolve_whatsapp_provider,
)


def test_meta_stub_send_text_ok():
    result = MetaCloudStubGateway().send_text(phone_e164="+5511999999999", text="oi")
    assert result["ok"] is True
    assert result["provider"] == "meta"
    assert result["ref"].startswith("wamid-stub-")


def test_meta_http_not_configured(settings):
    settings.META_WHATSAPP_TOKEN = ""
    settings.META_WHATSAPP_PHONE_NUMBER_ID = ""
    result = MetaCloudHttpGateway().send_text(phone_e164="+5511999999999", text="oi")
    assert result["ok"] is False
    assert result["provider"] == "meta"


def test_evolution_stub_send_media():
    from integrations.evolution.client import EvolutionStubGateway

    result = EvolutionStubGateway().send_media(
        phone_e164="+5511999999999",
        filename="nota.pdf",
        mime_type="application/pdf",
        data=b"%PDF-1.4",
    )
    assert result["ok"] is True
    assert result["provider"] == "evolution"
    assert result["bytes"] == 8


def test_evolution_http_send_media(monkeypatch, settings):
    from integrations.evolution.client import EvolutionHttpGateway

    settings.EVOLUTION_API_BASE_URL = "https://evo.example"
    settings.EVOLUTION_API_KEY = "key"
    settings.EVOLUTION_INSTANCE = "exeq"
    captured = {}

    class FakeResponse:
        status_code = 201

        def json(self):
            return {"key": {"id": "media-1"}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("integrations.evolution.client.httpx.Client", FakeClient)
    result = EvolutionHttpGateway().send_media(
        phone_e164="+5511999999999",
        filename="DANFSe.pdf",
        mime_type="application/pdf",
        data=b"%PDF-1.4",
        caption="DANFSe",
    )
    assert result["ok"] is True
    assert result["ref"] == "media-1"
    assert "sendMedia/exeq" in captured["url"]
    assert captured["json"]["mediatype"] == "document"
    assert captured["json"]["fileName"] == "DANFSe.pdf"
    assert captured["json"]["media"].startswith("data:application/pdf;base64,")


def test_meta_http_send_media(monkeypatch, settings):
    settings.META_WHATSAPP_TOKEN = "token-abc"
    settings.META_WHATSAPP_PHONE_NUMBER_ID = "123456"
    settings.META_GRAPH_API_VERSION = "v23.0"
    calls = []

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body
            self.text = ""

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None, data=None, files=None):
            calls.append({"url": url, "json": json, "data": data, "files": files})
            if "/media" in url and not url.endswith("/messages"):
                return FakeResponse(200, {"id": "media-xyz"})
            return FakeResponse(200, {"messages": [{"id": "wamid.doc"}]})

    monkeypatch.setattr("integrations.meta_cloud.client.httpx.Client", FakeClient)
    result = MetaCloudHttpGateway().send_media(
        phone_e164="+5511999999999",
        filename="nota.pdf",
        mime_type="application/pdf",
        data=b"%PDF-1.4",
    )
    assert result["ok"] is True
    assert result["ref"] == "wamid.doc"
    assert result["media_id"] == "media-xyz"
    assert len(calls) == 2
    assert calls[1]["json"]["type"] == "document"
    assert calls[1]["json"]["document"]["id"] == "media-xyz"


def test_meta_http_send_text(monkeypatch, settings):
    settings.META_WHATSAPP_TOKEN = "token-abc"
    settings.META_WHATSAPP_PHONE_NUMBER_ID = "123456"
    settings.META_GRAPH_API_VERSION = "v23.0"

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"messages": [{"id": "wamid.HBg"}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("integrations.meta_cloud.client.httpx.Client", FakeClient)

    result = MetaCloudHttpGateway().send_text(phone_e164="+5511999999999", text="ola")
    assert result["ok"] is True
    assert result["ref"] == "wamid.HBg"
    assert captured["url"] == "https://graph.facebook.com/v23.0/123456/messages"
    assert captured["headers"]["Authorization"] == "Bearer token-abc"
    assert captured["json"]["to"] == "5511999999999"
    assert captured["json"]["text"] == {"body": "ola"}
    assert captured["json"]["messaging_product"] == "whatsapp"


def test_get_meta_cloud_gateway_modes(settings):
    settings.META_WHATSAPP_HTTP_MODE = "stub"
    assert isinstance(get_meta_cloud_gateway(), MetaCloudStubGateway)
    settings.META_WHATSAPP_HTTP_MODE = "http"
    assert isinstance(get_meta_cloud_gateway(), MetaCloudHttpGateway)


class _TenantLike:
    def __init__(self, provider: str | None):
        self.settings = {"whatsapp_provider": provider} if provider else {}


def test_resolve_provider_defaults_to_evolution(settings):
    settings.WHATSAPP_PROVIDER = "evolution"
    assert resolve_whatsapp_provider() == "evolution"
    assert resolve_whatsapp_provider(_TenantLike(None)) == "evolution"


def test_resolve_provider_global_meta(settings):
    settings.WHATSAPP_PROVIDER = "meta"
    assert resolve_whatsapp_provider() == "meta"


def test_resolve_provider_tenant_overrides_global(settings):
    settings.WHATSAPP_PROVIDER = "evolution"
    assert resolve_whatsapp_provider(_TenantLike("meta")) == "meta"
    settings.WHATSAPP_PROVIDER = "meta"
    assert resolve_whatsapp_provider(_TenantLike("evolution")) == "evolution"


def test_resolve_provider_invalid_falls_back_to_evolution(settings):
    settings.WHATSAPP_PROVIDER = "banana"
    assert resolve_whatsapp_provider() == "evolution"
    assert resolve_whatsapp_provider(_TenantLike("xpto")) == "evolution"


def test_get_whatsapp_gateway_by_provider(settings):
    settings.WHATSAPP_PROVIDER = "evolution"
    settings.EVOLUTION_HTTP_MODE = "stub"
    assert isinstance(get_whatsapp_gateway(), EvolutionStubGateway)

    settings.WHATSAPP_PROVIDER = "meta"
    settings.META_WHATSAPP_HTTP_MODE = "stub"
    assert isinstance(get_whatsapp_gateway(), MetaCloudStubGateway)

    settings.META_WHATSAPP_HTTP_MODE = "http"
    assert isinstance(get_whatsapp_gateway(), MetaCloudHttpGateway)

    settings.WHATSAPP_PROVIDER = "evolution"
    settings.EVOLUTION_HTTP_MODE = "http"
    assert isinstance(get_whatsapp_gateway(), EvolutionHttpGateway)


@pytest.mark.django_db
def test_enqueue_notification_records_provider_per_tenant(tenant_a):
    from apps.channel.services import enqueue_notification

    tenant_a.settings = {"whatsapp_provider": "meta"}
    tenant_a.save(update_fields=["settings"])

    notification = enqueue_notification(
        tenant=tenant_a,
        phone_e164="+5511999999999",
        event_type="nf_issue.authorized",
        message_body="NFS-e autorizada",
    )
    assert notification.provider == "meta"
    assert notification.status == "sent"
    assert notification.provider_ref.startswith("wamid-stub-")


@pytest.mark.django_db
def test_enqueue_notification_defaults_to_evolution(tenant_a):
    from apps.channel.services import enqueue_notification

    notification = enqueue_notification(
        tenant=tenant_a,
        phone_e164="+5511888888888",
        event_type="nf_issue.authorized",
        message_body="NFS-e autorizada",
    )
    assert notification.provider == "evolution"
    assert notification.provider_ref.startswith("evo-")
