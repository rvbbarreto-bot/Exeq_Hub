"""Extração de campos do XML NFe 4.00 para DANFE (layout EXEQ I2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(parent: ET.Element | None, *names: str) -> str:
    if parent is None:
        return ""
    want = set(names)
    for el in parent:
        if _local(el.tag) in want and el.text:
            return (el.text or "").strip()
    return ""


def _find(root: ET.Element, name: str) -> ET.Element | None:
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


@dataclass
class DanfeFields:
    access_key: str = ""
    series: str = ""
    number: str = ""
    nature: str = ""
    issue_date: str = ""
    tp_amb: str = "2"
    protocol: str = ""
    emit_name: str = ""
    emit_cnpj: str = ""
    emit_ie: str = ""
    emit_address: str = ""
    emit_uf: str = ""
    dest_name: str = ""
    dest_doc: str = ""
    dest_address: str = ""
    dest_uf: str = ""
    total_nf: str = "0.00"
    products: str = "0.00"
    items: list[dict[str, str]] = field(default_factory=list)
    cancelled: bool = False


def extract_danfe_fields(xml_bytes: bytes, *, cancelled: bool = False) -> DanfeFields:
    root = ET.fromstring(xml_bytes)
    inf = _find(root, "infNFe")
    ide = _find(root, "ide")
    emit = _find(root, "emit")
    dest = _find(root, "dest")
    total = _find(root, "ICMSTot")
    prot = _find(root, "infProt")  # pode estar no nfeProc

    access = ""
    if inf is not None:
        rid = inf.get("Id") or ""
        if rid.startswith("NFe"):
            access = rid[3:]

    def addr_block(node: ET.Element | None, ender_name: str) -> tuple[str, str]:
        if node is None:
            return "", ""
        ender = None
        for el in node:
            if _local(el.tag) == ender_name:
                ender = el
                break
        if ender is None:
            return "", ""
        parts = [
            _text(ender, "xLgr"),
            _text(ender, "nro"),
            _text(ender, "xBairro"),
            _text(ender, "xMun"),
            _text(ender, "UF"),
            _text(ender, "CEP"),
        ]
        line = " ".join(p for p in parts if p)
        return line, _text(ender, "UF")

    emit_addr, emit_uf = addr_block(emit, "enderEmit")
    dest_addr, dest_uf = addr_block(dest, "enderDest")

    items: list[dict[str, str]] = []
    for det in root.iter():
        if _local(det.tag) != "det":
            continue
        prod = None
        for ch in det:
            if _local(ch.tag) == "prod":
                prod = ch
                break
        if prod is None:
            continue
        items.append(
            {
                "code": _text(prod, "cProd"),
                "desc": _text(prod, "xProd"),
                "ncm": _text(prod, "NCM"),
                "cfop": _text(prod, "CFOP"),
                "qty": _text(prod, "qCom"),
                "unit": _text(prod, "uCom"),
                "vun": _text(prod, "vUnCom"),
                "vprod": _text(prod, "vProd"),
            }
        )

    dest_doc = _text(dest, "CNPJ") or _text(dest, "CPF")
    return DanfeFields(
        access_key=access,
        series=_text(ide, "serie"),
        number=_text(ide, "nNF"),
        nature=_text(ide, "natOp"),
        issue_date=_text(ide, "dhEmi") or _text(ide, "dEmi"),
        tp_amb=_text(ide, "tpAmb") or "2",
        protocol=_text(prot, "nProt") if prot is not None else "",
        emit_name=_text(emit, "xNome"),
        emit_cnpj=_text(emit, "CNPJ"),
        emit_ie=_text(emit, "IE"),
        emit_address=emit_addr,
        emit_uf=emit_uf,
        dest_name=_text(dest, "xNome"),
        dest_doc=dest_doc,
        dest_address=dest_addr,
        dest_uf=dest_uf,
        total_nf=_text(total, "vNF") or "0.00",
        products=_text(total, "vProd") or "0.00",
        items=items,
        cancelled=cancelled,
    )
