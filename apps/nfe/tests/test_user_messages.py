"""Mensagens amigáveis NF-e."""

from apps.nfe.exceptions import NfeValidationError
from apps.nfe.user_messages import format_nfe_field_errors, parse_nfe_validation_error


def test_format_customer_address_errors_friendly():
    errors = [
        {"field": "customer.address.uf", "message": "UF do destinatário obrigatória"},
        {
            "field": "customer.address.codigo_ibge",
            "message": "código IBGE do município do destinatário obrigatório (7 dígitos)",
        },
    ]
    msg = format_nfe_field_errors(errors)
    assert "contador" in msg.lower()
    assert "destinatário" in msg.lower()
    assert "IBGE" in msg
    assert '[{"field"' not in msg


def test_parse_validation_error_suggests_customer_action():
    exc = NfeValidationError(
        '[{"field": "customer.address.uf", "message": "UF do destinatário obrigatória"}]'
    )
    msg, _, action = parse_nfe_validation_error(exc)
    assert action is not None
    assert action.get("hint") == "customer"
