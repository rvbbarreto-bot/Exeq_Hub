from django.http import HttpResponseForbidden

from shared.client_ip import ip_allowed
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


class AdminIpAllowlistMiddleware:
    """SEC-P1-05: restringe /admin/ a ADMIN_ALLOWED_IPS (vazio = lab, sem filtro)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""
        if path.startswith("/admin"):
            from django.conf import settings

            allowed = getattr(settings, "ADMIN_ALLOWED_IPS", None) or []
            if allowed and not ip_allowed(
                request,
                allowed=allowed,
                trust_x_forwarded_for=getattr(
                    settings, "ADMIN_TRUST_X_FORWARDED_FOR", False
                ),
            ):
                return HttpResponseForbidden("Admin IP não autorizado.")
        return self.get_response(request)
