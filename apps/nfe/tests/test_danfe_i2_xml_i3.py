"""I2 DANFE + integração com artefatos."""

from __future__ import annotations

import pytest

from apps.master_data.models import Customer, Provider, TaxRegime
from apps.nfe.artifacts import ensure_authorized_artifacts, has_danfe_pdf, has_xml_authorized
from apps.nfe.models import NfeInvoice
from apps.nfe.services import (
    allowed_actions,
    create_draft,
    create_product,
    emit_invoice,
    replace_items,
)
from integrations.sefaz_nfe.danfe import LAYOUT_VERSION, extract_danfe_fields, render_danfe_pdf
from integrations.sefaz_nfe.xml_nfe import HOMOLOG_DEST_NAME, build_nfe_xml


@pytest.fixture
def nfe_settings(settings):
    settings.NFE_ENABLED = True
    settings.NFE_HTTP_MODE = "stub"
    return settings


@pytest.fixture
def provider_sp(tenant_a):
    return Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="EXEQ LAB LTDA",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua Jose Florido",
            "numero": "121",
            "bairro": "Jardim Alvinopolis",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12942480",
            "codigo_ibge": "3504107",
        },
    )


@pytest.fixture
def customer_b2b(tenant_a):
    return Customer.objects.create(
        tenant=tenant_a,
        document="12345678909",
        document_type=Customer.DocumentType.CPF,
        name="Cliente B2B",
        address={
            "logradouro": "Av Teste",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12940000",
            "codigo_ibge": "3504107",
        },
    )


def _snap_minimal():
    return {
        "emitente": {
            "cnpj": "37229907000137",
            "ie": "123456789112",
            "name": "EXEQ LAB",
            "crt": "simples_nacional",
            "address": {
                "logradouro": "Rua A",
                "numero": "1",
                "bairro": "Centro",
                "municipio": "Atibaia",
                "uf": "SP",
                "cep": "12942480",
                "codigo_ibge": "3504107",
            },
        },
        "destinatario": {
            "document": "12345678909",
            "document_type": "cpf",
            "name": "Cliente",
            "address": {
                "logradouro": "Av B",
                "numero": "10",
                "bairro": "Centro",
                "municipio": "Atibaia",
                "uf": "SP",
                "cep": "12940000",
                "codigo_ibge": "3504107",
            },
        },
        "header": {
            "nature": "VENDA",
            "finality": "1",
            "series": 1,
            "number": 7,
            "tp_amb": "2",
            "issue_date": "2026-08-05",
            "ind_ie_dest": "9",
        },
        "items": [
            {
                "line": 1,
                "code": "SKU1",
                "description": "Produto",
                "ncm": "21069090",
                "cfop": "5102",
                "unit": "UN",
                "quantity": "2",
                "unit_price_cents": 10000,
                "total_cents": 20000,
                "origin": "0",
                "csosn": "102",
                "taxes": {
                    "origin": "0",
                    "icms": {"regime": "sn", "csosn": "102", "value_cents": 0},
                    "pis": {"cst": "07", "value_cents": 0, "rate_bp": 0, "base_cents": 0},
                    "cofins": {"cst": "07", "value_cents": 0, "rate_bp": 0, "base_cents": 0},
                },
            }
        ],
        "totals": {
            "products_cents": 20000,
            "total_cents": 20000,
            "freight_cents": 0,
            "discount_cents": 0,
            "icms_cents": 0,
            "pis_cents": 0,
            "cofins_cents": 0,
        },
        "payment": {"method": "99", "amount_cents": 20000},
    }


def test_render_danfe_pdf_from_xml():
    xml = build_nfe_xml(snapshot=_snap_minimal())
    pdf = render_danfe_pdf(xml)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500
    fields = extract_danfe_fields(xml)
    assert fields.series == "1"
    assert fields.number == "7"
    assert "37229907000137" in fields.emit_cnpj
    assert LAYOUT_VERSION


def test_render_danfe_cancelled_watermark():
    xml = build_nfe_xml(snapshot=_snap_minimal())
    pdf = render_danfe_pdf(xml, cancelled=True)
    assert pdf.startswith(b"%PDF")


def test_xml_i3_homolog_dest_and_id_dest():
    snap = _snap_minimal()
    xml = build_nfe_xml(snapshot=snap).decode("utf-8")
    assert HOMOLOG_DEST_NAME[:40] in xml
    assert "<idDest>1</idDest>" in xml or "idDest>1" in xml
    assert "ICMSSN102" in xml


def test_xml_i3_interestadual_id_dest():
    snap = _snap_minimal()
    snap["destinatario"]["address"]["uf"] = "MG"
    xml = build_nfe_xml(snapshot=snap).decode("utf-8")
    assert "idDest>2" in xml


def test_xml_empty_items_raises():
    snap = _snap_minimal()
    snap["items"] = []
    with pytest.raises(ValueError):
        build_nfe_xml(snapshot=snap)


@pytest.mark.django_db
def test_emit_stores_xml_and_danfe(nfe_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a,
        code="D1",
        description="Danfe item",
        ncm="21069090",
        unit_price_cents=2500,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="i2-emit-1",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "3"}])
    emit_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert has_xml_authorized(inv)
    assert has_danfe_pdf(inv)
    actions = allowed_actions(inv)
    assert "download_xml" in actions
    assert "download_pdf" in actions
    assert not (inv.last_validation or {}).get("pdf_pending")


@pytest.mark.django_db
def test_download_pdf_api(api_client, auth_header, nfe_settings, tenant_a, provider_sp, customer_b2b):
    product = create_product(
        tenant=tenant_a, code="D2", description="P", ncm="21069090", unit_price_cents=100
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="i2-dl-pdf",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    emit_invoice(inv)
    r = api_client.get(f"/api/v1/nfe/invoices/{inv.id}/artifacts/pdf", **auth_header)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
    assert "pdf" in r["Content-Type"]


@pytest.mark.django_db
def test_pdf_pending_does_not_clear_authorized(
    nfe_settings, tenant_a, provider_sp, customer_b2b, monkeypatch
):
    product = create_product(
        tenant=tenant_a, code="D3", description="P", ncm="21069090", unit_price_cents=100
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider_sp,
        customer=customer_b2b,
        idempotency_key="i2-pdf-fail",
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])

    def _boom(*_a, **_k):
        raise RuntimeError("render fail")

    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render.render_danfe_pdf",
        _boom,
    )
    monkeypatch.setattr(
        "integrations.sefaz_nfe.danfe.render_danfe_pdf",
        _boom,
    )
    emit_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == NfeInvoice.Status.AUTHORIZED
    assert has_xml_authorized(inv)
    assert not has_danfe_pdf(inv)
    assert (inv.last_validation or {}).get("pdf_pending") is True
