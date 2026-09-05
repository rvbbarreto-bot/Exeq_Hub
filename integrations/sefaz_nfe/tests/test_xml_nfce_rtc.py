"""XML NFC-e — Grupo UB RTC emit."""

from __future__ import annotations

from datetime import date

import pytest

from integrations.sefaz_nfe.xml_nfce import build_nfce_xml


def _emit_snapshot():
    return {
        "document_model": "65",
        "emitente": {
            "cnpj": "37229907000137",
            "name": "EXEQ PDV",
            "ie": "ISENTO",
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
        "header": {
            "model": "65",
            "nature": "VENDA",
            "series": 1,
            "number": 1,
            "tp_amb": "2",
            "issue_date": "2026-09-04",
            "omit_dest": True,
            "csc_id": "1",
            "csc_token": "HOMOLOGCSC",
        },
        "sefaz": {"csc_id": "1", "csc_token": "HOMOLOGCSC"},
        "items": [
            {
                "line": 1,
                "code": "SKU1",
                "description": "Produto",
                "ncm": "21069090",
                "cfop": "5102",
                "unit": "UN",
                "quantity": "1",
                "unit_price_cents": 10_000,
                "total_cents": 10_000,
                "origin": "0",
                "csosn": "102",
                "taxes": {
                    "icms": {"regime": "sn", "csosn": "102"},
                    "rtc": {
                        "mode": "emit",
                        "xml_ub": True,
                        "cst": "000",
                        "c_class_trib": "000001",
                        "base_cents": 10_000,
                        "p_cbs_bp": 90,
                        "p_ibs_bp": 10,
                        "v_cbs_cents": 90,
                        "v_ibs_cents": 10,
                        "v_ibs_uf_cents": 10,
                    },
                },
            }
        ],
        "totals": {
            "products_cents": 10_000,
            "total_cents": 10_000,
            "icms_cents": 0,
            "pis_cents": 0,
            "cofins_cents": 0,
            "rtc": {
                "base_cents": 10_000,
                "v_ibs_cents": 10,
                "v_cbs_cents": 90,
                "v_nftot_cents": 10_100,
            },
        },
        "payment": {"method": "99", "amount_cents": 10_000},
    }


def test_xml_nfce_rtc_emit_includes_ibscbs():
    xml = build_nfce_xml(snapshot=_emit_snapshot())
    text = xml.decode("utf-8")
    assert "<IBSCBS>" in text
    assert "<gIBSCBS>" in text
    assert "<IBSCBSTot>" in text
    assert "<vNFTot>101.00</vNFTot>" in text


@pytest.mark.django_db
def test_validation_includes_rtc_shadow(settings, tenant_a):
    from apps.accounts.tenant_emission import apply_emission_flags
    from apps.master_data.models import Provider, TaxRegime
    from apps.nfce.services import create_draft, replace_items, validate_invoice
    from apps.nfe.services import create_product

    settings.NFE_ENABLED = True
    settings.NFCE_ENABLED = True
    settings.NFCE_RTC_MODE = "shadow"
    tenant_a.settings = apply_emission_flags(
        tenant_a.settings, nfse=True, nfe=True, nfce=True
    )
    tenant_a.save(update_fields=["settings"])
    provider = Provider.objects.create(
        tenant=tenant_a,
        document="37229907000137",
        legal_name="RTC Tax",
        tax_regime=TaxRegime.SIMPLES,
        address={
            "logradouro": "Rua A",
            "numero": "1",
            "uf": "SP",
            "codigo_ibge": "3504107",
        },
        is_active=True,
    )
    product = create_product(
        tenant=tenant_a,
        code="RTC1",
        description="Item",
        ncm="21069090",
        unit_price_cents=10_000,
        csosn="102",
    )
    inv = create_draft(
        tenant=tenant_a,
        provider=provider,
        idempotency_key="rtc-val",
        issue_date=date(2026, 9, 4),
    )
    replace_items(inv, items=[{"product_id": str(product.id), "quantity": "1"}])
    inv.refresh_from_db()
    result = validate_invoice(inv)
    assert result["ok"] is True
    rtc = result["totals"]["rtc"]
    assert rtc["v_cbs_cents"] == 90
    assert result["items_taxes"][0]["taxes"]["rtc"]["mode"] == "shadow"
