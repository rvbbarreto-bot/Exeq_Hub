from shared.exceptions import DomainError


class ReceitaHttpNotConfiguredError(DomainError):
    code = "receita_http_not_configured"


class ReceitaAuthError(DomainError):
    code = "receita_auth_failed"


class ReceitaHttpError(DomainError):
    code = "receita_http_error"


class ReceitaBusinessError(DomainError):
    code = "receita_business_error"


class ReceitaCredentialsMissingError(DomainError):
    code = "receita_credentials_missing"
