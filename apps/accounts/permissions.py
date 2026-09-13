from rest_framework.permissions import BasePermission, SAFE_METHODS

WRITE_ROLES = frozenset({"tenant_admin", "operator"})
FOOD_ONLY_ROLES = frozenset({"food_operator"})
FOOD_WRITE_ROLES = WRITE_ROLES | FOOD_ONLY_ROLES
READ_ROLES = WRITE_ROLES | frozenset({"accountant", "readonly"}) | FOOD_ONLY_ROLES
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
        # Escritas gerais: não inclui food_only (só APIs food devem relaxar via papel)
        role = getattr(request, "role_code", None)
        if role in FOOD_ONLY_ROLES:
            return False
        return bool(
            request.user
            and request.user.is_authenticated
            and role in WRITE_ROLES
        )


class IsTenantFoodWriter(BasePermission):
    """POST/PATCH em endpoints Food — operator + food_operator."""

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return IsTenantMember().has_permission(request, view)
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "tenant", None)
            and getattr(request, "role_code", None) in FOOD_WRITE_ROLES
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
