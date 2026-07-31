"""Testes SEC-P1-05 Admin IP allowlist."""

from django.test import RequestFactory

from shared.middleware import AdminIpAllowlistMiddleware


def _mw(get_response=None):
    return AdminIpAllowlistMiddleware(
        get_response or (lambda r: type("R", (), {"status_code": 200})())
    )


def test_admin_ip_allowlist_empty_allows(settings):
    settings.ADMIN_ALLOWED_IPS = []
    req = RequestFactory().get("/admin/", REMOTE_ADDR="198.51.100.1")
    resp = _mw()(req)
    assert resp.status_code == 200


def test_admin_ip_allowlist_blocks_other(settings):
    settings.ADMIN_ALLOWED_IPS = ["203.0.113.10"]
    settings.ADMIN_TRUST_X_FORWARDED_FOR = False
    req = RequestFactory().get("/admin/login/", REMOTE_ADDR="198.51.100.1")
    resp = _mw()(req)
    assert resp.status_code == 403


def test_admin_ip_allowlist_allows_listed(settings):
    settings.ADMIN_ALLOWED_IPS = ["203.0.113.10"]
    req = RequestFactory().get("/admin/", REMOTE_ADDR="203.0.113.10")
    resp = _mw()(req)
    assert resp.status_code == 200


def test_admin_ip_allowlist_ignores_non_admin(settings):
    settings.ADMIN_ALLOWED_IPS = ["203.0.113.10"]
    req = RequestFactory().get("/api/v1/nf-issue/", REMOTE_ADDR="198.51.100.1")
    resp = _mw()(req)
    assert resp.status_code == 200
