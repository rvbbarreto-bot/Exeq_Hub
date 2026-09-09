"""Exceções do módulo NF-e de entrada."""


class NfeEntradaDomainError(Exception):
    code = "nfe_entrada_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class NfeEntradaDisabledError(NfeEntradaDomainError):
    code = "nfe_entrada_disabled"


class DistributionError(NfeEntradaDomainError):
    code = "nfe_entrada_distribution"


class ConsumptionLimitError(DistributionError):
    code = "nfe_entrada_consumption_limit"


class ManifestationError(NfeEntradaDomainError):
    code = "nfe_entrada_manifestation"


class DocumentProcessingError(NfeEntradaDomainError):
    code = "nfe_entrada_document"


class CertificateError(NfeEntradaDomainError):
    code = "nfe_entrada_certificate"
