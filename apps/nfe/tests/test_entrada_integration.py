"""Integração — fluxo sync → API → manifestação."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.nfe.entrada.models import NfeEntradaDocument
from apps.nfe.entrada.services.distribuicao import sync_distribuicao_once
from integrations.nfse.tests.pfx_factory import make_test_pfx
from integrations.sefaz_nfe.manifestacao.evento import TP_EVENTO_CIENCIA


@pytest.mark.django_db
def test_integration_sync_list_manifest(api_client, auth_header, entrada_settings, tenant_a, provider_sp):
    sync_distribuicao_once(tenant=tenant_a, provider=provider_sp, stub_mode="138")
    doc = NfeEntradaDocument.objects.filter(tenant=tenant_a).first()
    assert doc is not None

    listing = api_client.get(
        "/api/v1/nfe/entrada/?manifest_status=none&days=0",
        **auth_header,
    )
    assert listing.status_code == 200
    ids = [row["id"] for row in listing.data["results"]]
    assert str(doc.id) in ids

    pfx = make_test_pfx()
    with patch(
        "apps.nfe.entrada.services.manifestacao.load_primary_pfx_material",
        return_value=(pfx, "test"),
    ):
        manifest = api_client.post(
            f"/api/v1/nfe/entrada/{doc.id}/manifest/",
            {"tp_evento": TP_EVENTO_CIENCIA},
            format="json",
            **auth_header,
        )
    assert manifest.status_code == 201

    detail = api_client.get(f"/api/v1/nfe/entrada/{doc.id}/", **auth_header)
    assert detail.data["manifest_status"] == "ciencia"
    assert len(detail.data["manifestations"]) == 1


@pytest.mark.django_db
def test_integration_sync_config_and_status(api_client, auth_header, entrada_settings, provider_sp):
    r = api_client.post(
        "/api/v1/nfe/entrada/sync/",
        {"provider_id": str(provider_sp.id)},
        format="json",
        **auth_header,
    )
    assert r.status_code == 202

    status_r = api_client.get(
        f"/api/v1/nfe/entrada/distribution/status/?provider_id={provider_sp.id}",
        **auth_header,
    )
    assert status_r.data["ult_nsu"] != "0" or status_r.data["last_c_stat"] == "138"

    config_r = api_client.put(
        "/api/v1/nfe/entrada/distribution/config/",
        {
            "provider_id": str(provider_sp.id),
            "automatic_enabled": True,
            "interval_seconds": 3600,
        },
        format="json",
        **auth_header,
    )
    assert config_r.data["automatic_enabled"] is True


@pytest.mark.django_db
def test_integration_xml_download_when_available(
    api_client, auth_header, entrada_settings, tenant_a, provider_sp
):
    from apps.nfe.tests.test_entrada_document_service import _parsed
    from apps.nfe.entrada.services.document import upsert_entrada_document

    result = upsert_entrada_document(
        tenant=tenant_a,
        provider=provider_sp,
        parsed=_parsed(nsu="000000000000001", schema="procNFe"),
    )
    doc = result.document
    r = api_client.get(f"/api/v1/nfe/entrada/{doc.id}/xml/", **auth_header)
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/xml")
    assert b"resNFe" in r.content or b"nfeProc" in r.content or b"stub" in r.content.lower()


@pytest.mark.django_db
def test_integration_xml_pending_returns_404(api_client, auth_header, entrada_doc):
    r = api_client.get(f"/api/v1/nfe/entrada/{entrada_doc.id}/xml/", **auth_header)
    assert r.status_code == 404
    assert r.data["code"] == "nfe_entrada_xml_missing"
