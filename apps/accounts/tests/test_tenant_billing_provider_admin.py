"""Admin Tenant — config de provedor de cobrança."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.admin import TenantAdmin
from apps.accounts.models import Tenant


def _staff_request(method="get", path="/", data=None):
    User = get_user_model()
    user = User.objects.create_superuser(
        email="qa-tenant-admin@exeq.local",
        password="Secret123!",
        name="QA Tenant",
    )
    factory = RequestFactory()
    if method == "post":
        request = factory.post(path, data or {})
    else:
        request = factory.get(path)
    request.user = user
    setattr(request, "session", "session")
    setattr(request, "_messages", FallbackStorage(request))
    return request


@pytest.mark.django_db
def test_tenant_admin_billing_provider_get(tenant_a):
    site = AdminSite()
    model_admin = TenantAdmin(Tenant, site)
    request = _staff_request(
        path=reverse("admin:accounts_tenant_billing_provider", args=[tenant_a.pk])
    )
    response = model_admin.billing_provider_view(request, str(tenant_a.pk))
    assert response.status_code == 200
    html = response.rendered_content
    assert "Provedor" in html or "provedor" in html.lower()
    assert "inter" in html.lower()


@pytest.mark.django_db
def test_tenant_admin_set_provider_post(tenant_a, settings):
    settings.PAYMENT_HTTP_MODE = "stub"
    settings.INTER_WEBHOOK_PUBLIC_URL = ""
    site = AdminSite()
    model_admin = TenantAdmin(Tenant, site)
    path = reverse("admin:accounts_tenant_billing_provider", args=[tenant_a.pk])
    request = _staff_request(
        method="post",
        path=path,
        data={"action": "set_provider", "provider": "asaas"},
    )
    response = model_admin.billing_provider_view(request, str(tenant_a.pk))
    assert response.status_code == 302
    tenant_a.refresh_from_db()
    assert tenant_a.settings.get("payment_provider") == "asaas"
