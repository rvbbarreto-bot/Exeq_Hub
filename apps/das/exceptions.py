from shared.exceptions import DomainError


class DuplicateDasIdempotencyError(DomainError):
    code = "duplicate_das_idempotency"


class DuplicateDasNaturalKeyError(DomainError):
    code = "duplicate_das_natural_key"
