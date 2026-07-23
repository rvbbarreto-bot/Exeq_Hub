"""Unit tests: normalize Inter + Asaas webhook shapes."""

import pytest

from integrations.payments.normalize import normalize_gateway_payload


def test_normalize_canonical_passthrough():
    payload = {
        "tenant_slug": "acme",
        "idempotency_key": "k1",
        "gateway_ref": "inter_abc",
        "amount_cents": 1500,
    }
    out = normalize_gateway_payload(payload)
    assert out["amount_cents"] == 1500
    assert out["gateway_ref"] == "inter_abc"


def test_normalize_asaas_payment_event():
    payload = {
        "event": "PAYMENT_RECEIVED",
        "payment": {
            "id": "pay_123",
            "value": 12.34,
            "externalReference": "uuid-here",
            "confirmedDate": "2024-08-01T10:00:00Z",
        },
    }
    out = normalize_gateway_payload(payload)
    assert out["gateway_ref"] == "pay_123"
    assert out["amount_cents"] == 1234
    assert out["provider"] == "asaas"
    assert out["hub_status"] == "paid"
    assert out["idempotency_key"] == "PAYMENT_RECEIVED:pay_123"


def test_normalize_inter_recebido_full():
    payload = {
        "cobranca": {
            "codigoSolicitacao": "sol-1",
            "situacao": "RECEBIDO",
            "valorNominal": 50.0,
            "valorTotalRecebido": 50.0,
            "dataSituacao": "2026-07-20T15:00:00-03:00",
            "seuNumero": "CTRL01",
        }
    }
    out = normalize_gateway_payload(payload)
    assert out["provider"] == "inter"
    assert out["gateway_ref"] == "sol-1"
    assert out["amount_cents"] == 5000
    assert out["hub_status"] == "paid"
    assert out["event"] == "RECEBIDO"
    assert out["external_reference"] == "CTRL01"
    assert out["needs_enrich"] is False
    assert out["idempotency_key"].startswith("RECEBIDO:sol-1:")


def test_normalize_inter_light_callback():
    out = normalize_gateway_payload({"codigoSolicitacao": "sol-light"})
    assert out["provider"] == "inter"
    assert out["gateway_ref"] == "sol-light"
    assert out["needs_enrich"] is True
    assert "amount_cents" not in out
    assert out.get("hub_status") is None


def test_normalize_inter_a_receber_not_paid():
    payload = {
        "cobranca": {
            "codigoSolicitacao": "sol-2",
            "situacao": "A_RECEBER",
            "valorNominal": 10.0,
        }
    }
    out = normalize_gateway_payload(payload)
    assert out["hub_status"] == "registered"
    assert out["needs_enrich"] is False
    assert out["amount_cents"] == 1000


def test_normalize_inter_recebido_without_amount_needs_enrich():
    payload = {
        "codigoSolicitacao": "sol-3",
        "situacao": "MARCADO_RECEBIDO",
    }
    out = normalize_gateway_payload(payload)
    assert out["hub_status"] == "paid"
    assert out["needs_enrich"] is True


def test_normalize_unknown_shape_raises():
    with pytest.raises(ValueError, match="não suportado"):
        normalize_gateway_payload({"foo": "bar"})
