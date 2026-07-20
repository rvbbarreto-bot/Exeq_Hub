from shared.exceptions import DomainError


class InvalidTransitionError(DomainError):
    code = "invalid_transition"


class IssueNotFoundError(DomainError):
    code = "issue_not_found"


class FocusCancelFailedError(DomainError):
    code = "FOCUS_CANCEL_FAILED"


class CancelJustificationError(DomainError):
    code = "invalid_cancel_justification"


class FiscalProfileRequiredError(DomainError):
    code = "fiscal_profile_required"
