class DomainError(Exception):
    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class AuthenticationError(DomainError):
    code = "authentication_failed"
