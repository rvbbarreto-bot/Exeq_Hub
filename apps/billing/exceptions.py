from shared.exceptions import DomainError


class InvalidWebhookSignatureError(DomainError):
    code = "invalid_webhook_signature"


class ChargeNotFoundError(DomainError):
    code = "charge_not_found"


class IncompatiblePaymentError(DomainError):
    code = "incompatible_payment"


class GatewayRegistrationError(DomainError):
    code = "gateway_registration_failed"


class InvalidPaymentProviderError(DomainError):
    code = "invalid_payment_provider"


class InvalidProviderCredentialsError(DomainError):
    code = "invalid_provider_credentials"


class InvalidBillingPresetError(DomainError):
    code = "invalid_billing_preset"


class InvalidChargeInputError(DomainError):
    code = "invalid_charge_input"
