class NfceDomainError(Exception):
    code = "nfce_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class NfceDisabledError(NfceDomainError):
    code = "nfce_disabled"


class NfceValidationError(NfceDomainError):
    code = "nfce_validation"


class NfceInvalidTransitionError(NfceDomainError):
    code = "nfce_invalid_transition"


class NfceVersionConflictError(NfceDomainError):
    code = "nfce_version_conflict"


class NfceGateError(NfceDomainError):
    code = "nfce_gate"


class NfcePolicyError(NfceDomainError):
    code = "nfce_policy"
