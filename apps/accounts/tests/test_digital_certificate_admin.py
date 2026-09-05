"""Admin DigitalCertificate — bloqueio de cadastro manual; upload via Hub."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.accounts.admin import DigitalCertificateAdmin
from apps.accounts.models import DigitalCertificate


@pytest.fixture
def admin_client(db):
    User = get_user_model()
    user = User.objects.create_superuser(
        email="qa-cert-admin@exeq.local",
        password="Secret123!",
        name="QA Cert Admin",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_digital_certificate_admin_has_no_add_permission():
    site = AdminSite()
    model_admin = DigitalCertificateAdmin(DigitalCertificate, site)
    User = get_user_model()
    user = User.objects.create_superuser(
        email="perm@exeq.local", password="x", name="P"
    )
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.user = user
    assert model_admin.has_add_permission(request) is False


@pytest.mark.django_db
def test_digital_certificate_add_url_redirects_to_changelist(admin_client):
    add_url = reverse("admin:accounts_digitalcertificate_add")
    list_url = reverse("admin:accounts_digitalcertificate_changelist")
    response = admin_client.get(add_url)
    assert response.status_code == 302
    assert response.url == list_url


@pytest.mark.django_db
def test_digital_certificate_changelist_shows_hub_hint(admin_client):
    list_url = reverse("admin:accounts_digitalcertificate_changelist")
    hub_url = reverse("hub-v4-certificates")
    response = admin_client.get(list_url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "Hub" in html
    assert hub_url in html
    assert "PFX" in html.upper() or "pfx" in html
