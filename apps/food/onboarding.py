"""Onboarding idempotente — tenant Food QA + Mercado Pago."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.secrets import set_tenant_secret
from apps.accounts.membership_services import ensure_membership
from apps.accounts.services import ensure_system_roles
from apps.food.services import create_food_customer, create_food_product


@dataclass
class FoodOnboardResult:
    tenant_id: str
    tenant_slug: str
    user_email: str
    customer_with_email_id: str
    customer_without_email_id: str
    product_id: str
    created: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_slug": self.tenant_slug,
            "user_email": self.user_email,
            "customer_with_email_id": self.customer_with_email_id,
            "customer_without_email_id": self.customer_without_email_id,
            "product_id": self.product_id,
            "created": self.created,
            "notes": self.notes,
        }


def onboard_food_qa_tenant(
    *,
    slug: str = "food-qa",
    legal_name: str = "Food QA LTDA",
    document: str = "11222333000181",
    user_email: str = "qa.food@exeq.local",
    user_password: str = "Secret123!",
    role_code: str = "tenant_admin",
    mp_access_token: str = "",
    mp_public_key: str = "",
    mp_webhook_secret: str = "",
    product_sku: str = "QA-FOOD-01",
    product_name: str = "Produto QA Food",
    product_price_cents: int = 5000,
) -> FoodOnboardResult:
    """Provisiona tenant Food com Mercado Pago e catálogo mínimo de QA."""
    created: dict[str, bool] = {}
    notes: list[str] = []

    tenant = Tenant.objects.filter(slug=slug).first()
    if tenant is None:
        tenant = Tenant.objects.create(
            slug=slug,
            legal_name=legal_name,
            document="".join(ch for ch in document if ch.isdigit()),
            settings={},
        )
        created["tenant"] = True
    else:
        created["tenant"] = False

    settings = dict(tenant.settings or {})
    settings.update(
        {
            "food_payment_provider": "mercadopago",
            "food_payment_methods_enabled": ["pix", "card"],
            "payment_provider": settings.get("payment_provider") or "inter",
        }
    )
    if tenant.settings != settings:
        tenant.settings = settings
        tenant.save(update_fields=["settings", "updated_at"])
        notes.append("tenant.settings MP atualizado")

    roles = {r.code: r for r in ensure_system_roles()}
    role = roles.get(role_code)
    if role is None:
        raise ValueError(f"role inexistente: {role_code}")

    user = User.objects.filter(email__iexact=user_email).first()
    if user is None:
        if not user_password:
            raise ValueError("user_password obrigatório para criar usuário")
        user = User.objects.create_user(
            email=user_email,
            password=user_password,
            name=legal_name[:120] or user_email,
        )
        created["user"] = True
    else:
        created["user"] = False
        if user_password:
            user.set_password(user_password)
            user.save(update_fields=["password"])
            notes.append("user.password atualizado")

    membership, mem_created = ensure_membership(
        tenant=tenant,
        user=user,
        role=role,
        is_active=True,
    )
    created["membership"] = mem_created
    if not mem_created and membership.role_id != role.id:
        notes.append("membership.role atualizado")

    from apps.food.models import FoodCustomer, FoodProduct

    customer_email = FoodCustomer.objects.filter(
        tenant=tenant, email="maria.qa@example.com"
    ).first()
    if customer_email is None:
        customer_email = create_food_customer(
            tenant=tenant,
            name="Maria QA",
            phone_e164="+5511988880001",
            document="52998224725",
            email="maria.qa@example.com",
        )
        created["customer_with_email"] = True
    else:
        created["customer_with_email"] = False

    customer_no_email = FoodCustomer.objects.filter(
        tenant=tenant, name="João Sem Email"
    ).first()
    if customer_no_email is None:
        customer_no_email = create_food_customer(
            tenant=tenant,
            name="João Sem Email",
            phone_e164="+5511988880002",
            document="39053344705",
            email="",
        )
        created["customer_no_email"] = True
    else:
        created["customer_no_email"] = False

    product = FoodProduct.objects.filter(tenant=tenant, sku=product_sku).first()
    if product is None:
        product = create_food_product(
            tenant=tenant,
            sku=product_sku,
            name=product_name,
            price_cents=product_price_cents,
            cost_cents=2000,
            initial_stock=10,
        )
        created["product"] = True
    else:
        created["product"] = False

    secrets_created = False
    if mp_access_token:
        set_tenant_secret(
            tenant=tenant,
            provider="mercadopago",
            key_name="access_token",
            plaintext=mp_access_token,
        )
        secrets_created = True
    if mp_public_key:
        set_tenant_secret(
            tenant=tenant,
            provider="mercadopago",
            key_name="public_key",
            plaintext=mp_public_key,
        )
        secrets_created = True
    if mp_webhook_secret:
        set_tenant_secret(
            tenant=tenant,
            provider="mercadopago",
            key_name="webhook_secret",
            plaintext=mp_webhook_secret,
        )
        secrets_created = True
    created["tenant_secrets"] = secrets_created
    if not secrets_created:
        notes.append(
            "TenantSecret MP omitido (use --mp-access-token etc. ou FOOD_MP_WEBHOOK_SECRET no .env)"
        )

    return FoodOnboardResult(
        tenant_id=str(tenant.id),
        tenant_slug=tenant.slug,
        user_email=user.email,
        customer_with_email_id=str(customer_email.id),
        customer_without_email_id=str(customer_no_email.id),
        product_id=str(product.id),
        created=created,
        notes=notes,
    )
