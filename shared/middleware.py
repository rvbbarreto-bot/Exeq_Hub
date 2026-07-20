from shared.rls import clear_rls, set_rls


class TenantRLSMiddleware:
    """Inicia request com bypass; JWT auth restringe ao tenant; limpa no fim."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_rls(bypass=True)
        try:
            return self.get_response(request)
        finally:
            clear_rls()
