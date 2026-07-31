from shared.exceptions import DomainError


class CadastroDocumentInvalidError(DomainError):
    code = "cadastro_document_invalid"


class CadastroCpfLookupNotSupportedError(DomainError):
    code = "cadastro_cpf_lookup_not_supported"


class CadastroNotFoundError(DomainError):
    code = "cadastro_not_found"


class CadastroProviderUnavailableError(DomainError):
    code = "cadastro_provider_unavailable"
