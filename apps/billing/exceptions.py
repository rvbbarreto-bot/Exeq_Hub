from shared.exceptions import DomainError


class InvalidWebhookSignatureError(DomainError):
    code = "invalid_webhook_signature"


class ChargeNotFoundError(DomainError):
    code = "charge_not_found"


class IncompatiblePaymentError(DomainError):
    code = "incompatible_payment"


class GatewayRegistrationError(DomainError):
    code = "gateway_registration_failed"
