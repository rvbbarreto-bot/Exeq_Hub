"""Extração fiscal XML NFC-e mod 65 → campos DANFE (exeq-danfce-1.0)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from integrations.nfse.xml_safe import safe_fromstring
from integrations.sefaz_nfe.danfe_nfce.format import sum_item_quantities


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(parent: Any | None, *names: str) -> str:
    if parent is None:
        return ""
    want = set(names)
    for el in parent:
        if _local(el.tag) in want and el.text is not None:
            return (el.text or "").strip()
    return ""


def _find(root: Any, name: str) -> Any | None:
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


def _find_all(parent: Any, name: str) -> list[Any]:
    if parent is None:
        return []
    return [el for el in parent if _local(el.tag) == name]


@dataclass
class DanfceFields:
    access_key: str = ""
    series: str = ""
    number: str = ""
    issue_date: str = ""
    tp_amb: str = "2"
    protocol: str = ""
    auth_datetime: str = ""
    emit_name: str = ""
    emit_cnpj: str = ""
    emit_ie: str = ""
    emit_address: str = ""
    emit_uf: str = ""
    dest_name: str = ""
    dest_doc: str = ""
    dest_kind: str = ""  # cpf | cnpj | foreign | none
    total_nf: str = "0.00"
    products: str = "0.00"
    discount: str = "0.00"
    freight: str = "0.00"
    v_tot_trib: str = ""
    v_cbs: str = ""
    v_ibs: str = ""
    v_bc_rtc: str = ""
    item_count: int = 0
    total_units: str = "0"
    items: list[dict[str, str]] = field(default_factory=list)
    payments: list[dict[str, str]] = field(default_factory=list)
    change: str = ""
    url_chave: str = ""
    qr_code: str = ""
    cancelled: bool = False


def extract_danfce_fields(
    xml_bytes: bytes,
    *,
    cancelled: bool = False,
    protocol_override: str = "",
    auth_at_override: str = "",
) -> DanfceFields:
    root = safe_fromstring(xml_bytes)
    inf = _find(root, "infNFe")
    ide = _find(root, "ide")
    emit = _find(root, "emit")
    dest = _find(root, "dest")
    icmstot = _find(root, "ICMSTot")
    prot = _find(root, "infProt")
    supl = _find(root, "infNFeSupl")
    ibs_tot = _find(root, "IBSCBSTot")

    access = ""
    if inf is not None:
        rid = inf.get("Id") or ""
        if rid.startswith("NFe"):
            access = rid[3:]

    def addr_block(node: Any | None, ender_name: str) -> tuple[str, str]:
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
        ]
        line = ", ".join(p for p in parts[:2] if p)
        tail = " - ".join(p for p in parts[2:] if p)
        full = f"{line} - {tail}" if line and tail else (line or tail)
        return full, _text(ender, "UF")

    emit_addr, emit_uf = addr_block(emit, "enderEmit")

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
        n_item = det.get("nItem") or str(len(items) + 1)
        items.append(
            {
                "n_item": str(n_item),
                "code": _text(prod, "cProd"),
                "desc": _text(prod, "xProd"),
                "qty": _text(prod, "qCom"),
                "unit": _text(prod, "uCom") or "UN",
                "vun": _text(prod, "vUnCom"),
                "vprod": _text(prod, "vProd"),
            }
        )

    dest_cnpj = _text(dest, "CNPJ")
    dest_cpf = _text(dest, "CPF")
    dest_foreign = _text(dest, "idEstrangeiro")
    dest_kind = "none"
    dest_doc = ""
    if dest_cnpj:
        dest_kind, dest_doc = "cnpj", dest_cnpj
    elif dest_cpf:
        dest_kind, dest_doc = "cpf", dest_cpf
    elif dest_foreign:
        dest_kind, dest_doc = "foreign", dest_foreign

    payments: list[dict[str, str]] = []
    pag = _find(root, "pag")
    if pag is not None:
        for detpag in _find_all(pag, "detPag"):
            payments.append(
                {
                    "tPag": _text(detpag, "tPag") or "99",
                    "vPag": _text(detpag, "vPag") or "0.00",
                }
            )
        change = _text(pag, "vTroco")
    else:
        change = ""

    protocol = (protocol_override or "").strip() or (
        _text(prot, "nProt") if prot is not None else ""
    )
    auth_dt = (auth_at_override or "").strip() or (
        _text(prot, "dhRecbto") if prot is not None else ""
    )

    return DanfceFields(
        access_key=access,
        series=_text(ide, "serie"),
        number=_text(ide, "nNF"),
        issue_date=_text(ide, "dhEmi") or _text(ide, "dEmi"),
        tp_amb=_text(ide, "tpAmb") or "2",
        protocol=protocol,
        auth_datetime=auth_dt,
        emit_name=_text(emit, "xNome"),
        emit_cnpj=_text(emit, "CNPJ") or _text(emit, "CPF"),
        emit_ie=_text(emit, "IE"),
        emit_address=emit_addr,
        emit_uf=emit_uf,
        dest_name=_text(dest, "xNome"),
        dest_doc=dest_doc,
        dest_kind=dest_kind,
        total_nf=_text(icmstot, "vNF") or "0.00",
        products=_text(icmstot, "vProd") or "0.00",
        discount=_text(icmstot, "vDesc") or "0.00",
        freight=_text(icmstot, "vFrete") or "0.00",
        v_tot_trib=_text(icmstot, "vTotTrib") or "",
        v_cbs=_text(ibs_tot, "vCBS") if ibs_tot is not None else "",
        v_ibs=_text(ibs_tot, "vIBS") if ibs_tot is not None else "",
        v_bc_rtc=_text(ibs_tot, "vBCIBSCBS") if ibs_tot is not None else "",
        item_count=len(items),
        total_units=sum_item_quantities(items),
        items=items,
        payments=payments,
        change=change,
        url_chave=_text(supl, "urlChave") if supl is not None else "",
        qr_code=_text(supl, "qrCode") if supl is not None else "",
        cancelled=cancelled,
    )
