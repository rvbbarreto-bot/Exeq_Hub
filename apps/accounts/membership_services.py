"""Vínculos de usuário no tenant com teto de plano (max_users)."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.accounts.models import TenantMembership, TenantRole
from apps.accounts.plan_limits import assert_can_add_active_user
from apps.accounts.services import SYSTEM_ROLES, ensure_system_roles

User = get_user_model()

ASSIGNABLE_ROLE_CODES = frozenset(code for code, _ in SYSTEM_ROLES)


def ensure_membership(
    *,
    tenant,
    user,
    role,
    is_active: bool = True,
) -> tuple[TenantMembership, bool]:
    """
    get_or_create de membership com enforcement de max_users ao
    criar novo ativo ou reativar vínculo.
    """
    existing = TenantMembership.objects.filter(tenant=tenant, user=user).first()
    if existing is None:
        if is_active:
            assert_can_add_active_user(tenant)
        mem = TenantMembership.objects.create(
            tenant=tenant,
            user=user,
            role=role,
            is_active=is_active,
        )
        return mem, True

    dirty = False
    if is_active and not existing.is_active:
        assert_can_add_active_user(tenant)
        existing.is_active = True
        dirty = True
    if existing.role_id != role.id:
        existing.role = role
        dirty = True
    if dirty:
        existing.save()
    return existing, False


def _role_by_code(role_code: str) -> TenantRole:
    code = (role_code or "").strip()
    if code not in ASSIGNABLE_ROLE_CODES:
        raise ValueError(
            f"Papel inválido. Use: {', '.join(sorted(ASSIGNABLE_ROLE_CODES))}."
        )
    ensure_system_roles()
    role = TenantRole.objects.filter(code=code).first()
    if role is None:
        raise ValueError(f"Papel inexistente: {code}")
    return role


def count_active_tenant_admins(tenant, *, exclude_membership_id=None) -> int:
    qs = TenantMembership.objects.filter(
        tenant=tenant,
        is_active=True,
        role__code="tenant_admin",
    )
    if exclude_membership_id:
        qs = qs.exclude(pk=exclude_membership_id)
    return qs.count()


def invite_or_link_user(
    *,
    tenant,
    email: str,
    name: str = "",
    password: str = "",
    role_code: str = "operator",
    is_active: bool = True,
    generate_password_if_missing: bool = False,
) -> tuple[TenantMembership, bool, bool, str]:
    """
    Cria usuário se necessário e vincula ao tenant.
    Returns (membership, membership_created, user_created, plain_password_if_new).
    plain_password_if_new só quando user_created e senha gerada/setada neste convite.
    """
    email_norm = User.objects.normalize_email((email or "").strip())
    if not email_norm:
        raise ValueError("Informe o e-mail.")
    role = _role_by_code(role_code)
    name_clean = (name or "").strip() or email_norm.split("@")[0]

    user = User.objects.filter(email=email_norm).first()
    user_created = False
    plain_password = ""
    pwd = (password or "").strip()

    if user is None:
        if len(pwd) < 8:
            if generate_password_if_missing:
                from apps.accounts.invite_email import generate_temporary_password

                pwd = generate_temporary_password()
                plain_password = pwd
            else:
                raise ValueError("Senha com no mínimo 8 caracteres para novo usuário.")
        else:
            plain_password = pwd
        user = User.objects.create_user(
            email=email_norm,
            password=pwd,
            name=name_clean,
        )
        user_created = True
    else:
        if pwd:
            if len(pwd) < 8:
                raise ValueError("Senha com no mínimo 8 caracteres.")
            user.set_password(pwd)
            user.save(update_fields=["password"])
            plain_password = pwd
        if name_clean and user.name != name_clean:
            user.name = name_clean
            user.save(update_fields=["name", "updated_at"])

    mem, mem_created = ensure_membership(
        tenant=tenant,
        user=user,
        role=role,
        is_active=is_active,
    )
    return mem, mem_created, user_created, plain_password


def update_membership(
    *,
    membership: TenantMembership,
    role_code: str | None = None,
    is_active: bool | None = None,
    name: str | None = None,
    password: str = "",
    actor_user=None,
) -> TenantMembership:
    """Atualiza vínculo; protege último tenant_admin e self-lockout."""
    role = membership.role
    if role_code is not None:
        role = _role_by_code(role_code)

    new_active = membership.is_active if is_active is None else bool(is_active)

    # Reativar ocupa slot
    if new_active and not membership.is_active:
        assert_can_add_active_user(membership.tenant)

    losing_admin = (
        membership.is_active
        and membership.role.code == "tenant_admin"
        and (not new_active or role.code != "tenant_admin")
    )
    if losing_admin:
        remaining = count_active_tenant_admins(
            membership.tenant, exclude_membership_id=membership.pk
        )
        if remaining < 1:
            raise ValueError(
                "Não é possível remover ou desativar o último administrador do escritório."
            )

    if actor_user is not None and actor_user.pk == membership.user_id:
        if not new_active:
            raise ValueError("Você não pode desativar o próprio vínculo.")
        if membership.role.code == "tenant_admin" and role.code != "tenant_admin":
            remaining = count_active_tenant_admins(
                membership.tenant, exclude_membership_id=membership.pk
            )
            if remaining < 1:
                raise ValueError(
                    "Transfira o papel de administrador a outro usuário antes de rebaixar o seu."
                )

    membership.role = role
    membership.is_active = new_active
    membership.save(update_fields=["role", "is_active", "updated_at"])

    user = membership.user
    dirty_user = []
    if name is not None:
        n = name.strip()
        if n and n != user.name:
            user.name = n
            dirty_user.append("name")
    if password and password.strip():
        if len(password.strip()) < 8:
            raise ValueError("Senha com no mínimo 8 caracteres.")
        user.set_password(password.strip())
        dirty_user.append("password")
    if dirty_user:
        if "name" in dirty_user:
            dirty_user.append("updated_at")
        user.save(update_fields=list(dict.fromkeys(dirty_user)))

    return membership
