"""Marketplace HTTP sync + normalização."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.food.models import FoodOrder
from apps.food.operations import (
    sync_marketplace_connection,
    upsert_marketplace_connection,
)
from apps.food.services import create_food_product
from integrations.marketplace.factory import build_marketplace_gateway
from integrations.marketplace.normalize import normalize_marketplace_order


@pytest.fixture
def product(tenant_a):
    return create_food_product(
        tenant=tenant_a,
        sku="FAR-01",
        name="Farinha",
        price_cents=1500,
        cost_cents=500,
        unit="kg",
        initial_stock=Decimal("20"),
    )


@pytest.mark.django_db
def test_normalize_ifood_like_payload():
    raw = {
        "id": "IFO-HTTP-1",
        "customer": {"name": "Maria", "phone": "11987654321"},
        "items": [
            {"externalCode": "FAR-01", "quantity": 2, "unitPrice": 15.0},
        ],
        "total": {"orderAmount": 30.0},
        "delivery": {
            "deliveryAddress": {
                "streetName": "Rua X",
                "streetNumber": "10",
                "neighborhood": "Centro",
            }
        },
    }
    out = normalize_marketplace_order(
        provider="ifood", raw=raw, merchant_ref="loja-1"
    )
    assert out["external_order_id"] == "IFO-HTTP-1"
    assert out["customer_phone"].startswith("+55")
    assert out["lines"][0]["sku"] == "FAR-01"
    assert out["lines"][0]["unit_price_cents"] == 1500
    assert out["total_cents"] == 3000
    assert "Rua X" in out["delivery_address"]


@pytest.mark.django_db
def test_sync_stub_orders(tenant_a, product, settings):
    settings.MARKETPLACE_HTTP_MODE = "stub"
    conn = upsert_marketplace_connection(
        tenant=tenant_a,
        provider="ifood",
        merchant_ref="loja-stub",
        settings={
            "http_mode": "stub",
            "stub_orders": [
                {
                    "external_order_id": "STUB-1",
                    "customer_name": "Stub Buyer",
                    "customer_phone": "+5511911112222",
                    "lines": [
                        {
                            "sku": "FAR-01",
                            "quantity": "1",
                            "unit_price_cents": 1500,
                        }
                    ],
                    "total_cents": 1500,
                    "paid": True,
                }
            ],
        },
    )
    stats = sync_marketplace_connection(tenant=tenant_a, connection=conn)
    assert stats["fetched"] == 1
    assert stats["imported"] == 1
    assert stats["skipped"] == 0
    order = FoodOrder.objects.get(tenant=tenant_a, channel_ref="STUB-1")
    assert order.channel == FoodOrder.Channel.IFOOD
    assert order.marketplace_connection_id == conn.id

    again = sync_marketplace_connection(tenant=tenant_a, connection=conn)
    assert again["skipped"] == 1
    assert again["imported"] == 0


@pytest.mark.django_db
def test_sync_http_orders(tenant_a, product, settings):
    settings.MARKETPLACE_HTTP_MODE = "http"
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "orders": [
            {
                "id": "HTTP-99",
                "customer": {"name": "Http", "phone": "+5511933334444"},
                "items": [
                    {
                        "sku": "FAR-01",
                        "quantity": 1,
                        "unit_price_cents": 1500,
                    }
                ],
                "total_cents": 1500,
            }
        ]
    }
    session.get.return_value = resp

    conn = upsert_marketplace_connection(
        tenant=tenant_a,
        provider="aiqfome",
        merchant_ref="aq-1",
        settings={
            "http_mode": "http",
            "base_url": "https://mp.example.test",
            "access_token": "tok",
        },
    )
    stats = sync_marketplace_connection(
        tenant=tenant_a, connection=conn, session=session
    )
    assert stats["imported"] == 1
    session.get.assert_called_once()
    order = FoodOrder.objects.get(channel_ref="HTTP-99")
    assert order.channel == FoodOrder.Channel.AIQFOME


@pytest.mark.django_db
def test_api_marketplace_sync(api_client, auth_header, tenant_a, product, settings):
    settings.MARKETPLACE_HTTP_MODE = "stub"
    upsert_marketplace_connection(
        tenant=tenant_a,
        provider="ifood",
        merchant_ref="api-loja",
        settings={
            "stub_orders": [
                {
                    "external_order_id": "API-SYNC-1",
                    "customer_name": "Api Sync",
                    "lines": [{"sku": product.sku, "quantity": "1"}],
                    "paid": True,
                }
            ]
        },
    )
    r = api_client.post("/api/v1/food/marketplace/sync", {}, format="json", **auth_header)
    assert r.status_code == 200, r.content
    assert r.data["results"][0]["imported"] == 1


def test_build_gateway_modes(settings):
    settings.MARKETPLACE_HTTP_MODE = "stub"
    g = build_marketplace_gateway(provider="ifood", conn_settings={})
    assert g.__class__.__name__ == "StubMarketplaceGateway"
    settings.MARKETPLACE_HTTP_MODE = "http"
    g2 = build_marketplace_gateway(
        provider="ifood",
        conn_settings={"http_mode": "stub"},  # force stub
    )
    assert g2.__class__.__name__ == "StubMarketplaceGateway"
