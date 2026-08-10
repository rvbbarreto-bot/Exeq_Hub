class NfeDomainError(Exception):
    code = "nfe_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class NfeDisabledError(NfeDomainError):
    code = "nfe_disabled"


class NfeValidationError(NfeDomainError):
    code = "nfe_validation"


class NfeInvalidTransitionError(NfeDomainError):
    code = "nfe_invalid_transition"


class NfeVersionConflictError(NfeDomainError):
    code = "nfe_version_conflict"


class NfeGateError(NfeDomainError):
    code = "nfe_gate"
