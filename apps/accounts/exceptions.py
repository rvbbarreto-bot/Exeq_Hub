from shared.exceptions import DomainError


class CertificateNotUsableError(DomainError):
    code = "certificate_not_usable"


class ElectronicProxyNotUsableError(DomainError):
    code = "electronic_proxy_not_usable"
