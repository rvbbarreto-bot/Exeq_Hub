"""Fase 3 — WA-SEC: autenticação, tenant por instância, isolamento, mascaramento."""

import pytest

from apps.channel.models import ChannelSession
from apps.channel.webhook import mask_phone, mask_sensitive, parse_inbound_payload

PHONE = "+5511999990000"
TOKEN_HDR = {"HTTP_X_EXEQ_WEBHOOK_TOKEN": "test-webhook-token"}


@pytest.fixture
def channel_tenant(tenant_a):
    tenant_a.settings = {
        "whatsapp_authorized_phones": [PHONE],
        "evolution_instance": "exeq-lab",
    }
    tenant_a.save(update_fields=["settings"])
    return tenant_a


def _native_payload(*, instance="exeq-lab", text="quero emitir", msg_id="native-1", from_me=False):
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {
                "remoteJid": "5511999990000@s.whatsapp.net",
                "fromMe": from_me,
                "id": msg_id,
            },
            "message": {"conversation": text},
        },
        "apikey": "forged-body-key-must-be-ignored",
    }


@pytest.mark.django_db
def test_wa_sec_01_webhook_without_token_rejected(api_client, channel_tenant):
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        _native_payload(),
        format="json",
    )
    assert response.status_code == 401
    assert response.data["code"] == "webhook_unauthorized"
    assert ChannelSession.objects.filter(tenant=channel_tenant).count() == 0


@pytest.mark.django_db
def test_wa_sec_01_body_apikey_alone_not_enough(api_client, channel_tenant):
    """apikey no body Evolution não autentica — só header."""
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        {**_native_payload(), "apikey": "test-webhook-token"},
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_wa_sec_01_header_apikey_accepted(api_client, channel_tenant):
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        _native_payload(),
        format="json",
        HTTP_APIKEY="test-webhook-token",
    )
    assert response.status_code == 200
    assert response.data["status"] == "collecting"


@pytest.mark.django_db
def test_wa_sec_02_tenant_from_instance_ignores_spoofed_slug(
    api_client, channel_tenant, tenant_b
):
    """tenant_slug no body não muda o tenant — instância autentica o destino."""
    tenant_b.settings = {"evolution_instance": "other-instance"}
    tenant_b.save(update_fields=["settings"])

    payload = _native_payload(instance="exeq-lab", text="oi")
    payload["tenant_slug"] = tenant_b.slug  # spoof

    response = api_client.post(
        "/api/v1/webhooks/evolution",
        payload,
        format="json",
        **TOKEN_HDR,
    )
    assert response.status_code == 200
    assert response.data["status"] == "collecting"
    assert ChannelSession.objects.filter(tenant=channel_tenant).count() == 1
    assert ChannelSession.objects.filter(tenant=tenant_b).count() == 0


@pytest.mark.django_db
def test_wa_sec_02_unknown_instance_404(api_client, channel_tenant):
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        _native_payload(instance="ghost"),
        format="json",
        **TOKEN_HDR,
    )
    assert response.status_code == 404
    assert response.data["code"] == "instancia_desconhecida"


@pytest.mark.django_db
def test_wa_sec_02_from_me_ignored(api_client, channel_tenant):
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        _native_payload(from_me=True),
        format="json",
        **TOKEN_HDR,
    )
    assert response.status_code == 200
    assert response.data["status"] == "ignored"
    assert ChannelSession.objects.filter(tenant=channel_tenant).count() == 0


@pytest.mark.django_db
def test_wa_sec_03_sessions_isolated_by_tenant(
    api_client, auth_header, channel_tenant, tenant_b
):
    ChannelSession.objects.create(
        tenant=channel_tenant,
        idempotency_key=f"{PHONE}:iso",
        phone_e164=PHONE,
        draft_payload={},
    )
    ChannelSession.objects.create(
        tenant=tenant_b,
        idempotency_key=f"{PHONE}:iso-b",
        phone_e164=PHONE,
        draft_payload={},
    )
    response = api_client.get("/api/v1/channel/sessions/", **auth_header)
    assert response.status_code == 200
    ids = [row["id"] for row in response.data["results"]] if "results" in response.data else [
        row["id"] for row in response.data
    ]
    # auth_header é do tenant_a — só vê sessões dele
    assert len(ids) == 1
    assert ChannelSession.objects.get(pk=ids[0]).tenant_id == channel_tenant.id


@pytest.mark.django_db
def test_wa_sec_04_replay_same_message_id(api_client, channel_tenant):
    payload = _native_payload(msg_id="replay-1", text="oi")
    first = api_client.post(
        "/api/v1/webhooks/evolution", payload, format="json", **TOKEN_HDR
    )
    second = api_client.post(
        "/api/v1/webhooks/evolution", payload, format="json", **TOKEN_HDR
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data.get("reply") in ("", None) or ChannelSession.objects.filter(
        tenant=channel_tenant
    ).count() == 1
    assert ChannelSession.objects.filter(tenant=channel_tenant).count() == 1


def test_wa_sec_05_mask_sensitive_documents():
    assert "529***25" in mask_sensitive("CPF 529.982.247-25 ok")
    assert "***" in mask_sensitive("12.345.678/0001-90")
    assert mask_phone("+5511999990000") == "***0000"


@pytest.mark.django_db
def test_parse_native_extended_text(channel_tenant):
    outcome = parse_inbound_payload(
        {
            "event": "MESSAGES_UPSERT",
            "instance": "exeq-lab",
            "data": {
                "key": {
                    "remoteJid": "5511999990000@s.whatsapp.net",
                    "fromMe": False,
                    "id": "ext-1",
                },
                "message": {"extendedTextMessage": {"text": "CONFIRMAR"}},
            },
        }
    )
    assert outcome.status == "ok"
    assert outcome.inbound is not None
    assert outcome.inbound.text == "CONFIRMAR"
    assert outcome.inbound.tenant.id == channel_tenant.id


@pytest.mark.django_db
def test_legacy_disabled_rejects_simplified(api_client, channel_tenant, settings):
    settings.EVOLUTION_WEBHOOK_ALLOW_LEGACY = False
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        {
            "tenant_slug": "acme",
            "phone_e164": PHONE,
            "message_id": "leg-1",
            "text": "oi",
        },
        format="json",
        **TOKEN_HDR,
    )
    assert response.status_code == 400
