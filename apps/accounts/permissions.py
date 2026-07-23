from rest_framework.permissions import BasePermission, SAFE_METHODS

WRITE_ROLES = frozenset({"tenant_admin", "operator"})
READ_ROLES = WRITE_ROLES | frozenset({"accountant", "readonly"})
ADMIN_ROLES = frozenset({"tenant_admin"})


class IsTenantMember(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "tenant", None)
            and getattr(request, "role_code", None) in READ_ROLES
        )


class IsTenantWriter(BasePermission):
    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return IsTenantMember().has_permission(request, view)
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "role_code", None) in WRITE_ROLES
        )


class IsTenantAdmin(BasePermission):
    """Credenciais, provedor e webhook Inter — só tenant_admin."""

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return IsTenantMember().has_permission(request, view)
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "tenant", None)
            and getattr(request, "role_code", None) in ADMIN_ROLES
        )
