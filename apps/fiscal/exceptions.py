from shared.exceptions import DomainError


class CatalogNotEditableError(DomainError):
    code = "catalog_not_editable"


class PublishChecklistIncompleteError(DomainError):
    code = "publish_checklist_incomplete"

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Checklist incompleto: {', '.join(missing)}", code=self.code)


class TaxRuleNotFoundError(DomainError):
    code = "tax_rule_not_found"


class NationalCatalogError(DomainError):
    code = "national_catalog_error"


class RtcClassificationError(DomainError):
    code = "rtc_classification_error"
