import pytest

from apps.channel.models import ChannelSession
from apps.channel.services import ingest_inbound_message


@pytest.mark.django_db
def test_debounce_same_window_single_session(tenant_a):
    first = ingest_inbound_message(
        tenant=tenant_a,
        phone_e164="+5511999999999",
        message_id="m1",
        text="ola",
    )
    second = ingest_inbound_message(
        tenant=tenant_a,
        phone_e164="+5511999999999",
        message_id="m2",
        text="quero nota",
    )
    assert first.id == second.id
    assert ChannelSession.objects.filter(tenant=tenant_a).count() == 1
    second.refresh_from_db()
    assert second.draft_payload["text"] == "quero nota"


@pytest.mark.django_db
def test_same_message_id_idempotent(tenant_a):
    a = ingest_inbound_message(
        tenant=tenant_a,
        phone_e164="+5511888888888",
        message_id="dup",
        text="a",
    )
    b = ingest_inbound_message(
        tenant=tenant_a,
        phone_e164="+5511888888888",
        message_id="dup",
        text="b",
    )
    assert a.id == b.id


@pytest.mark.django_db
def test_evolution_webhook_api(api_client, tenant_a):
    response = api_client.post(
        "/api/v1/webhooks/evolution",
        {
            "tenant_slug": "acme",
            "phone_e164": "+5511777777777",
            "message_id": "w1",
            "text": "emitir",
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == "collecting"
