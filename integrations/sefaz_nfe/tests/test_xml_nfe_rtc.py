"""XML NF-e — Grupo UB RTC emit (W03)."""

from __future__ import annotations

from integrations.sefaz_nfe.xml_nfe import build_nfe_xml


def _emit_snapshot():
    return {
        "emitente": {
            "cnpj": "37229907000137",
            "name": "EXEQ LAB",
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
        "destinatario": {
            "document": "12345678909",
            "document_type": "cpf",
            "name": "Cliente",
            "address": {
                "logradouro": "Av B",
                "numero": "2",
                "bairro": "Centro",
                "municipio": "Atibaia",
                "uf": "SP",
                "cep": "12940000",
                "codigo_ibge": "3504107",
            },
            "ind_ie_dest": "9",
        },
        "header": {
            "nature": "VENDA",
            "finality": "1",
            "series": 1,
            "number": 1,
            "tp_amb": "2",
            "issue_date": "2026-09-04",
            "ind_ie_dest": "9",
            "consumer_final": "1",
            "buyer_presence": "9",
            "freight_mod": "9",
        },
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
        "payment": {"method": "99", "amount_cents": 10_100},
    }


def test_xml_nfe_rtc_emit_includes_ibscbs_and_w03():
    xml = build_nfe_xml(snapshot=_emit_snapshot())
    text = xml.decode("utf-8")
    assert "<IBSCBS>" in text
    assert "<gIBSCBS>" in text
    assert "<IBSCBSTot>" in text
    assert "<vNFTot>101.00</vNFTot>" in text
    assert "<vPag>101.00</vPag>" in text
