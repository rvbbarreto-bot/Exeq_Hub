"""Testes unitários assinatura webhook MP."""

from apps.food.payments.mercadopago.webhook_security import (
    build_signature_manifest,
    verify_mercadopago_signature,
)
from apps.food.webhook_views import sign_mercadopago_webhook_test


def test_verify_mercadopago_signature_roundtrip():
    secret = "test-secret"
    data_id = "12345"
    request_id = "req-abc"
    ts = "1704908010"
    header = sign_mercadopago_webhook_test(
        secret=secret,
        data_id=data_id,
        request_id=request_id,
        ts=ts,
    )
    manifest = build_signature_manifest(
        data_id=data_id,
        request_id=request_id,
        ts=ts,
    )
    assert "id:12345" in manifest
    assert verify_mercadopago_signature(
        secret=secret,
        x_signature=header,
        x_request_id=request_id,
        data_id=data_id,
    )
