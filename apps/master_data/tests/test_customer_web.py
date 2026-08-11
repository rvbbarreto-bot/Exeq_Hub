"""Cadastros /cadastros/ descontinuados — redirect para Hub V4."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_cadastros_routes_redirect_to_hub(client):
    for path in (
        "/cadastros/",
        "/cadastros/login/",
        "/cadastros/customers/",
        "/cadastros/customers/novo/",
        "/cadastros/providers/",
    ):
        response = client.get(path)
        assert response.status_code == 302, path
        assert response.url == "/hub/", path
