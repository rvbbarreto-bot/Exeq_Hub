"""Seed estático do catálogo mercadorias MVP (substituível por import CSV)."""

from __future__ import annotations

# NCM lab + varejo SN (herda allowlist apps/nfe/catalog.py)
NCM_ITEMS: tuple[tuple[str, str], ...] = (
    ("21069090", "Preparações alimentícias n.e."),
    ("22021000", "Águas, incl. minerais e gaseificadas"),
    ("22030000", "Cervejas de malte"),
    ("30049099", "Medicamentos dosados"),
    ("33049910", "Produtos de beleza/makeup"),
    ("34011190", "Sabões de toucador"),
    ("39269090", "Plásticos e obras, n.e."),
    ("40169990", "Obras de borracha vulcanizada n.e."),
    ("48201000", "Cadernos"),
    ("49019900", "Livros, brochuras e impressos"),
    ("61091000", "Camisetas de malha"),
    ("62034200", "Calças de algodão"),
    ("63026000", "Roupas de cama de algodão"),
    ("64029990", "Calçados com sola e parte superior de borracha/plástico"),
    ("84713012", "Máquinas automáticas processamento dados — portáteis"),
    ("84713019", "Máquinas automáticas processamento dados — outras"),
    ("85171231", "Telefones celulares"),
    ("85285220", "Monitores com tubo"),
    ("87089990", "Partes e acessórios veículos automóveis"),
    ("94036000", "Móveis de madeira"),
)

CFOP_ITEMS: tuple[tuple[str, str, str], ...] = (
    # code, description, scope: internal|interstate|both
    ("5101", "Venda produção do estabelecimento", "internal"),
    ("5102", "Venda mercadoria adquirida/recebida de terceiros", "internal"),
    ("5405", "Venda mercadoria sujeita ST (contribuinte)", "internal"),
    ("5910", "Bonificação, doação ou brinde", "internal"),
    ("6101", "Venda produção — interestadual", "interstate"),
    ("6102", "Venda mercadoria adquirida — interestadual", "interstate"),
    ("6405", "Venda mercadoria sujeita ST — interestadual", "interstate"),
    ("6910", "Bonificação/doação — interestadual", "interstate"),
)

UNIT_ITEMS: tuple[tuple[str, str], ...] = (
    ("UN", "Unidade"),
    ("KG", "Quilograma"),
    ("G", "Grama"),
    ("L", "Litro"),
    ("ML", "Mililitro"),
    ("CX", "Caixa"),
    ("FD", "Fardo"),
    ("PC", "Peça"),
    ("PCT", "Pacote"),
    ("PAR", "Par"),
    ("M", "Metro"),
    ("M2", "Metro quadrado"),
    ("M3", "Metro cúbico"),
    ("TON", "Tonelada"),
    ("SC", "Saco"),
    ("DZ", "Dúzia"),
    ("HR", "Hora"),
)

FALLBACK_VERSION = "goods-mvp-1.0"
