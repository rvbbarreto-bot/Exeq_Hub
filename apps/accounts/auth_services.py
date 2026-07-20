from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Tenant, TenantMembership, User
from shared.exceptions import AuthenticationError


def authenticate_for_tenant(*, tenant_slug: str, email: str, password: str) -> tuple[User, TenantMembership]:
    try:
        tenant = Tenant.objects.get(slug=tenant_slug)
    except Tenant.DoesNotExist as exc:
        raise AuthenticationError("Credenciais inválidas") from exc

    if tenant.status != Tenant.Status.ACTIVE:
        raise AuthenticationError("Tenant indisponível")

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist as exc:
        raise AuthenticationError("Credenciais inválidas") from exc

    if not user.is_active or not user.check_password(password):
        raise AuthenticationError("Credenciais inválidas")

    try:
        membership = TenantMembership.objects.select_related("role", "tenant").get(
            tenant=tenant,
            user=user,
            is_active=True,
        )
    except TenantMembership.DoesNotExist as exc:
        raise AuthenticationError("Credenciais inválidas") from exc

    user.last_login_at = timezone.now()
    user.save(update_fields=["last_login_at", "updated_at"])
    return user, membership


def issue_tokens(user: User, membership: TenantMembership) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    claims = {
        "tenant_id": str(membership.tenant_id),
        "tenant_slug": membership.tenant.slug,
        "role_code": membership.role.code,
    }
    for key, value in claims.items():
        refresh[key] = value
        refresh.access_token[key] = value
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "tenant_slug": membership.tenant.slug,
        "role_code": membership.role.code,
    }
