from apps.accounts.models import TenantRole

SYSTEM_ROLES: tuple[tuple[str, str], ...] = (
    ("tenant_admin", "Tenant Admin"),
    ("operator", "Operator"),
    ("accountant", "Accountant"),
    ("readonly", "Read Only"),
)


def ensure_system_roles() -> list[TenantRole]:
    roles: list[TenantRole] = []
    for code, name in SYSTEM_ROLES:
        role, _ = TenantRole.objects.get_or_create(
            code=code,
            defaults={"name": name, "is_system": True, "permissions": []},
        )
        roles.append(role)
    return roles
