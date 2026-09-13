"""Checklist spec CONSTRUFORTI / UniDANFE 3.9.13."""

from __future__ import annotations

import io

from pypdf import PdfReader

from integrations.sefaz_nfe.danfe.formatters import (
    addresses_differ,
    format_nf_number,
    format_phone_br,
)
from integrations.sefaz_nfe.danfe.pagination import plan_pages
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, render_danfe_moc_pdf
from integrations.sefaz_nfe.danfe.viewmodel import AddressView, build_danfe_viewmodel
from integrations.sefaz_nfe.tests.danfe_fixtures import xml_rich_blocks_homolog


def test_layout_version_spec():
    assert LAYOUT_VERSION == "exeq-danfe-2.7.7-spec"


def test_format_nf_number_thousands():
    assert format_nf_number("3925") == "3.925"


def test_format_phone_br():
    assert format_phone_br("1144116980") == "(11) 4411-6980"


def test_delivery_only_when_address_differs():
    dest = AddressView(logradouro="RUA A", numero="1", bairro="CENTRO", municipio="ATIBAIA", uf="SP", cep="12942480")
    same = AddressView(logradouro="RUA A", numero="1", bairro="CENTRO", municipio="ATIBAIA", uf="SP", cep="12942480")
    other = AddressView(logradouro="RUA B", numero="2", bairro="JARDIM", municipio="ATIBAIA", uf="SP", cep="12946000")
    assert not addresses_differ(dest.compare_key, same.compare_key)
    assert addresses_differ(dest.compare_key, other.compare_key)


def test_rich_fixture_shows_delivery_and_tax_approx():
    xml = xml_rich_blocks_homolog()
    vm = build_danfe_viewmodel(xml)
    assert vm.delivery_differs_from_dest
    assert vm.items[0].ean == "7898908622980"
    pages = plan_pages(vm)
    assert pages[0].show_delivery is True

    pdf = render_danfe_moc_pdf(xml)
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "VALOR APROX" in text.upper()
    assert "CSOSN" in text.upper() or "0102" in text or "102" in text
    assert "COD. BARRAS" in text.upper() or "7898908622980" in text
    assert "RECEBEMOS DE" in text.upper()
    assert "0-REMETENTE" in text.upper() or "0-REM" in text.upper()
    assert "ENTRADA" in text.upper() and "SAIDA" in text.upper()
    assert "(15,0000%)" in text or "15,0000%" in text
    assert "PROTOCOLO DE AUTORIZACAO" in text.upper()
    assert "135260000000001" in text.replace(" ", "")
