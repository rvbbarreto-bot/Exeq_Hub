"""Erros de integração marketplace Food."""


class MarketplaceError(Exception):
    code = "marketplace_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class MarketplaceConfigError(MarketplaceError):
    code = "marketplace_config"


class MarketplaceHttpError(MarketplaceError):
    code = "marketplace_http"
