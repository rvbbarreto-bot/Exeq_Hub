from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from apps.accounts.models import Tenant, TenantMembership
from shared.rls import set_rls


class TenantJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result
        tenant_id = validated_token.get("tenant_id")
        if not tenant_id:
            raise InvalidToken("Token sem tenant")

        try:
            membership = TenantMembership.objects.select_related("tenant", "role").get(
                tenant_id=tenant_id,
                user=user,
                is_active=True,
            )
        except TenantMembership.DoesNotExist as exc:
            raise InvalidToken("Membership inválida") from exc

        if membership.tenant.status != Tenant.Status.ACTIVE:
            raise InvalidToken("Tenant indisponível")

        request.tenant = membership.tenant
        request.membership = membership
        request.role_code = membership.role.code
        set_rls(tenant_id=str(membership.tenant_id), bypass=False)
        return user, validated_token
