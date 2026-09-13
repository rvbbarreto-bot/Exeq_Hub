"""Fixtures compartilhadas — testes DANFE NF-e."""

from __future__ import annotations

from integrations.sefaz_nfe.access_key import build_access_key
from integrations.sefaz_nfe.nfe_proc import authorized_xml_bytes
from integrations.sefaz_nfe.tests.test_nfe_proc import _SNAP
from integrations.sefaz_nfe.xml_nfe import build_nfe_xml

_GOLDEN_KEY = build_access_key(
    uf="SP",
    issue_date_iso="2026-08-05",
    cnpj="37229907000137",
    series=1,
    number=1,
    cnf=12345678,
)
_GOLDEN_PROT = "135260000000001"


def xml_multipage_homolog(n_items: int = 35) -> bytes:
    """Fixture determinística para DANFE multi-página (homolog)."""
    return xml_with_items(n_items, desc="Item", tp_amb="2")


def xml_long_infcpl_homolog(*, n_items: int = 1, n_cpl_lines: int = 12) -> bytes:
    """NF-e com infCpl longo — força folha extra de continuação."""
    snap = dict(_SNAP)
    snap["header"] = {**snap["header"], "tp_amb": "2"}
    paragraphs = [f"Linha{i:02d} informacao complementar extensa para paginacao DANFE." for i in range(1, n_cpl_lines + 1)]
    snap["inf_adic"] = {"infCpl": " ".join(paragraphs), "infAdFisco": "Reservado teste."}
    items = []
    for i in range(1, n_items + 1):
        items.append(
            {
                "line": i,
                "code": f"SKU{i}",
                "description": f"Produto {i}",
                "ncm": "21069090",
                "cfop": "5102",
                "unit": "UN",
                "quantity": "1",
                "unit_price_cents": 1000,
                "taxes": {"icms": {"regime": "sn", "csosn": "102"}, "pis": {"cst": "49"}, "cofins": {"cst": "49"}},
            }
        )
    snap["items"] = items
    snap["totals"] = {"products_cents": 1000 * n_items, "total_cents": 1000 * n_items}
    snap["payment"] = {"method": "99", "amount_cents": 1000 * n_items}
    nfe = build_nfe_xml(snapshot=snap, access_key=_GOLDEN_KEY)
    return authorized_xml_bytes(signed_nfe_xml=nfe, access_key=_GOLDEN_KEY, protocol=_GOLDEN_PROT, tp_amb="2") or nfe


def xml_rich_blocks_homolog(*, n_items: int = 1) -> bytes:
    """NF-e com fatura, transporte e blocos MOC Fase D."""
    snap = dict(_SNAP)
    snap["header"] = {
        **snap["header"],
        "tp_amb": "2",
        "nature": "VENDA DE MERCADORIA",
        "freight_mod": "0",
        "exit_date": "2026-08-05",
    }
    snap["emitente"] = {
        **snap["emitente"],
        "phone": "1144445555",
    }
    snap["billing"] = {
        "nFat": "001",
        "vOrig": "100.00",
        "vLiq": "100.00",
        "duplicates": [
            {"nDup": "001", "dVenc": "2026-09-05", "vDup": "50.00"},
            {"nDup": "002", "dVenc": "2026-10-05", "vDup": "50.00"},
        ],
    }
    snap["transport"] = {
        "modFrete": "0",
        "carrier": {
            "name": "TRANSPORTADORA EXEMPLO LTDA",
            "document": "61536366000174",
            "ie": "123456789112",
            "city": "Atibaia",
            "uf": "SP",
        },
        "volume": {"qVol": "2", "esp": "CAIXA", "marca": "EXEQ", "pesoB": "10.500", "pesoL": "9.800"},
        "vehicle": {"placa": "ABC1D23", "uf": "SP"},
    }
    snap["entrega"] = {
        "document": "44509800000108",
        "address": {
            "logradouro": "Rua Obra 500",
            "numero": "S/N",
            "bairro": "Jardim Industrial",
            "municipio": "Atibaia",
            "uf": "SP",
            "cep": "12946000",
            "codigo_ibge": "3504107",
        },
    }
    snap["inf_adic"] = {
        "infCpl": "Pedido 12345 — entrega agendada.",
        "infAdFisco": "Sem informações.",
    }
    snap["totals"] = {
        "products_cents": 1000 * n_items,
        "total_cents": 1000 * n_items,
        "freight_cents": 0,
        "v_tot_trib_cents": 150,
    }
    items = []
    for i in range(1, n_items + 1):
        items.append(
            {
                "line": i,
                "code": f"SKU{i}",
                "description": f"Produto fiscal {i}",
                "ncm": "21069090",
                "cfop": "5102",
                "unit": "UN",
                "quantity": "1",
                "unit_price_cents": 1000,
                "gtin": "7898908622980",
                "taxes": {
                    "icms": {
                        "regime": "sn",
                        "csosn": "102",
                        "xml_group": "ICMSSN102",
                    },
                    "pis": {"cst": "49"},
                    "cofins": {"cst": "49"},
                    "v_tot_trib_cents": 10044,
                },
            }
        )
    snap["items"] = items
    snap["payment"] = {"method": "99", "amount_cents": 1000 * n_items}
    nfe = build_nfe_xml(snapshot=snap, access_key=_GOLDEN_KEY)
    return (
        authorized_xml_bytes(
            signed_nfe_xml=nfe,
            access_key=_GOLDEN_KEY,
            protocol=_GOLDEN_PROT,
            tp_amb="2",
        )
        or nfe
    )


def xml_with_items(n_items: int, *, desc: str = "Produto", tp_amb: str = "2") -> bytes:
    snap = dict(_SNAP)
    snap["header"] = {**snap["header"], "tp_amb": tp_amb}
    items = []
    for i in range(1, n_items + 1):
        items.append(
            {
                "line": i,
                "code": f"SKU{i}",
                "description": desc if i == 1 else f"{desc} {i}",
                "ncm": "21069090",
                "cfop": "5102",
                "unit": "UN",
                "quantity": "1",
                "unit_price_cents": 1000,
                "taxes": {
                    "icms": {"regime": "sn", "csosn": "102"},
                    "pis": {"cst": "49"},
                    "cofins": {"cst": "49"},
                },
            }
        )
    snap["items"] = items
    snap["totals"] = {"products_cents": 1000 * n_items, "total_cents": 1000 * n_items}
    snap["payment"] = {"method": "99", "amount_cents": 1000 * n_items}
    nfe = build_nfe_xml(snapshot=snap, access_key=_GOLDEN_KEY)
    return (
        authorized_xml_bytes(
            signed_nfe_xml=nfe,
            access_key=_GOLDEN_KEY,
            protocol=_GOLDEN_PROT,
            tp_amb=tp_amb,
        )
        or nfe
    )
