"""DANFEViewModel — camada A (XML/domínio → modelo normalizado para PDF)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from integrations.nfse.xml_safe import safe_fromstring
from integrations.sefaz_nfe.danfe.formatters import addresses_differ, digits_only, format_cep

NFE_NS = "http://www.portalfiscal.inf.br/nfe"

# tpEmis → rótulo contingência (domínio; renderer só exibe)
_TP_EMIS_LABELS = {
    "1": "normal",
    "2": "contingencia_fs",
    "3": "contingencia_scan",
    "4": "contingencia_dpec",
    "5": "contingencia_fs_da",
    "6": "contingencia_svc_an",
    "7": "contingencia_svc_rs",
    "9": "contingencia_offline",
}

# Consulta por UF — não hard-code URL única universal (§12)
_UF_CONSULTA_HINT = {
    "SP": "Consulta em www.nfe.fazenda.gov.br/portal ou portal SEFAZ-SP",
}


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(parent: Any | None, *names: str) -> str:
    if parent is None:
        return ""
    want = set(names)
    for el in parent:
        if _local(el.tag) in want and el.text:
            return (el.text or "").strip()
    return ""


def _find(root: Any, name: str) -> Any | None:
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


def _findall(root: Any, name: str) -> list[Any]:
    return [el for el in root.iter() if _local(el.tag) == name]


@dataclass(frozen=True)
class TaxClassification:
    kind: str  # CST | CSOSN
    code: str

    @property
    def display(self) -> str:
        if not self.code:
            return ""
        if self.kind == "CSOSN":
            return self.code
        return self.code


@dataclass(frozen=True)
class AddressView:
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    municipio: str = ""
    uf: str = ""
    cep: str = ""

    @property
    def street_line(self) -> str:
        parts = [self.logradouro, self.numero]
        if self.complemento:
            parts.append(self.complemento)
        return ", ".join(p for p in parts if p)

    @property
    def city_line(self) -> str:
        cep = format_cep(self.cep)
        city = self.municipio
        uf = self.uf
        if cep and city and uf:
            return f"{cep} {city} - {uf}"
        return " - ".join(p for p in (cep, city, uf) if p)

    @property
    def compare_key(self) -> str:
        def norm(part: str) -> str:
            return " ".join((part or "").upper().split())

        return "|".join(
            [
                norm(self.logradouro),
                norm(self.numero),
                norm(self.bairro),
                norm(self.municipio),
                norm(self.uf),
                digits_only(self.cep),
            ]
        )


@dataclass
class DanfeItemView:
    line: str = ""
    code: str = ""
    description: str = ""
    ean: str = ""
    ncm: str = ""
    tax_classification: TaxClassification = field(default_factory=lambda: TaxClassification("CST", ""))
    cfop: str = ""
    unit: str = ""
    quantity: str = ""
    unit_price: str = ""
    total: str = ""
    discount: str = ""
    icms_base: str = ""
    icms_st_base: str = ""
    icms_value: str = ""
    icms_st_value: str = ""
    ipi_value: str = ""
    icms_rate: str = ""
    ipi_rate: str = ""
    approx_taxes: str = ""


@dataclass
class DanfeDuplicateView:
    number: str = ""
    due_date: str = ""
    amount: str = ""


@dataclass
class DanfeTransportView:
    freight_mod: str = ""
    carrier_name: str = ""
    carrier_doc: str = ""
    carrier_ie: str = ""
    carrier_address: str = ""
    carrier_city: str = ""
    carrier_uf: str = ""
    vehicle_plate: str = ""
    vehicle_uf: str = ""
    volumes_qty: str = ""
    volumes_species: str = ""
    volumes_brand: str = ""
    volumes_number: str = ""
    gross_weight: str = ""
    net_weight: str = ""


@dataclass
class DanfeTotalsView:
    icms_base: str = "0.00"
    icms_value: str = "0.00"
    icms_st_base: str = "0.00"
    icms_st_value: str = "0.00"
    products: str = "0.00"
    freight: str = "0.00"
    insurance: str = "0.00"
    discount: str = "0.00"
    other: str = "0.00"
    ipi_value: str = "0.00"
    pis_value: str = "0.00"
    cofins_value: str = "0.00"
    total_nf: str = "0.00"
    approx_taxes: str = ""


@dataclass
class DanfeAuthorizationView:
    protocol: str = ""
    authorized_at: str = ""
    c_stat: str = ""
    x_motivo: str = ""
    tp_emis: str = "1"
    emission_mode: str = "normal"
    is_contingency: bool = False


@dataclass
class DanfeViewModel:
    access_key: str = ""
    tp_nf: str = "1"
    series: str = ""
    number: str = ""
    nature: str = ""
    issue_date: str = ""
    exit_date: str = ""
    tp_amb: str = "2"
    emit_name: str = ""
    emit_fantasy: str = ""
    emit_cnpj: str = ""
    emit_ie: str = ""
    emit_ie_st: str = ""
    emit_crt: str = ""
    emit_address: str = ""
    emit_address_line1: str = ""
    emit_address_line2: str = ""
    emit_phone: str = ""
    emit_uf: str = ""
    dest_name: str = ""
    dest_doc: str = ""
    dest_ie: str = ""
    dest_address: str = ""
    dest_address_parts: AddressView = field(default_factory=AddressView)
    dest_phone: str = ""
    dest_uf: str = ""
    delivery_address: str = ""
    delivery_name: str = ""
    delivery_doc: str = ""
    delivery_ie: str = ""
    delivery_address_parts: AddressView = field(default_factory=AddressView)
    has_entrega: bool = False
    delivery_differs_from_dest: bool = False
    items: list[DanfeItemView] = field(default_factory=list)
    totals: DanfeTotalsView = field(default_factory=DanfeTotalsView)
    transport: DanfeTransportView = field(default_factory=DanfeTransportView)
    duplicates: list[DanfeDuplicateView] = field(default_factory=list)
    invoice_number_fat: str = ""
    invoice_value_fat: str = ""
    inf_cpl: str = ""
    inf_ad_fisco: str = ""
    authorization: DanfeAuthorizationView = field(default_factory=DanfeAuthorizationView)
    consultation_hint: str = ""
    cancelled: bool = False
    logo_bytes: bytes | None = None


def _tax_from_icms(icms_parent: Any | None) -> TaxClassification:
    if icms_parent is None:
        return TaxClassification("CST", "")
    for el in icms_parent:
        tag = _local(el.tag)
        if tag.startswith("ICMSSN"):
            return TaxClassification("CSOSN", _text(el, "CSOSN"))
        if tag.startswith("ICMS"):
            return TaxClassification("CST", _text(el, "CST"))
    return TaxClassification("CST", "")


def _icms_values(icms_parent: Any | None) -> tuple[str, str, str, str, str]:
    if icms_parent is None:
        return "", "", "", "", ""
    for el in icms_parent:
        tag = _local(el.tag)
        if tag.startswith("ICMS"):
            return (
                _text(el, "vBC"),
                _text(el, "vICMS"),
                _text(el, "vBCST"),
                _text(el, "vICMSST"),
                _text(el, "pICMS"),
            )
    return "", "", "", "", ""


def _ipi_value(imposto: Any | None) -> tuple[str, str]:
    if imposto is None:
        return "", ""
    ipi = None
    for ch in imposto:
        if _local(ch.tag) == "IPI":
            ipi = ch
            break
    if ipi is None:
        return "", ""
    for grp in ipi:
        t = _local(grp.tag)
        if t.startswith("IPITrib") or t.startswith("IPINT"):
            return _text(grp, "vIPI"), _text(grp, "pIPI")
    return "", ""


def _parse_ender(node: Any | None, ender_name: str) -> AddressView:
    if node is None:
        return AddressView()
    ender = None
    for el in node:
        if _local(el.tag) == ender_name:
            ender = el
            break
    if ender is None:
        return AddressView()
    return AddressView(
        logradouro=_text(ender, "xLgr"),
        numero=_text(ender, "nro"),
        complemento=_text(ender, "xCpl"),
        bairro=_text(ender, "xBairro"),
        municipio=_text(ender, "xMun"),
        uf=_text(ender, "UF"),
        cep=_text(ender, "CEP"),
    )


def _parse_entrega(inf: Any | None) -> tuple[bool, str, str, str, AddressView]:
    if inf is None:
        return False, "", "", "", AddressView()
    entrega = None
    for el in inf:
        if _local(el.tag) == "entrega":
            entrega = el
            break
    if entrega is None:
        return False, "", "", "", AddressView()
    addr = AddressView(
        logradouro=_text(entrega, "xLgr"),
        numero=_text(entrega, "nro"),
        complemento=_text(entrega, "xCpl"),
        bairro=_text(entrega, "xBairro"),
        municipio=_text(entrega, "xMun"),
        uf=_text(entrega, "UF"),
        cep=_text(entrega, "CEP"),
    )
    doc = _text(entrega, "CNPJ") or _text(entrega, "CPF")
    return True, _text(entrega, "xNome"), doc, _text(entrega, "IE"), addr


def _addr_block(node: Any | None, ender_name: str) -> tuple[str, str, str, AddressView]:
    addr = _parse_ender(node, ender_name)
    phone = ""
    if node is not None:
        ender = None
        for el in node:
            if _local(el.tag) == ender_name:
                ender = el
                break
        if ender is not None:
            phone = _text(ender, "fone")
    line = ", ".join(p for p in (addr.street_line, addr.bairro, addr.city_line) if p)
    return line, addr.uf, phone, addr


def _is_simples_nacional(crt: str) -> bool:
    return crt in {"1", "2", "3"}


def _valid_ean(value: str) -> str:
    raw = (value or "").upper()
    if "SEM GTIN" in raw:
        return ""
    digits = digits_only(value)
    if not digits or set(digits) == {"0"}:
        return ""
    if len(digits) in (8, 12, 13, 14):
        return digits
    return ""


def build_danfe_viewmodel(xml_bytes: bytes, *, cancelled: bool = False) -> DanfeViewModel:
    """XML/NFe/nfeProc → DANFEViewModel (sem cálculos fiscais)."""
    root = safe_fromstring(xml_bytes)
    inf = _find(root, "infNFe")
    ide = _find(root, "ide")
    emit = _find(root, "emit")
    dest = _find(root, "dest")
    total = _find(root, "ICMSTot")
    prot = _find(root, "infProt")
    transp = _find(root, "transp")
    inf_adic = _find(root, "infAdic")
    fat = _find(root, "fat")

    access = ""
    if inf is not None:
        rid = inf.get("Id") or ""
        if rid.startswith("NFe"):
            access = rid[3:]
    if not access and prot is not None:
        access = _text(prot, "chNFe")

    emit_addr, emit_uf, emit_phone, emit_parts = _addr_block(emit, "enderEmit")
    dest_addr, dest_uf, dest_phone, dest_parts = _addr_block(dest, "enderDest")
    has_entrega, delivery_name, delivery_doc, delivery_ie, delivery_parts = _parse_entrega(inf)
    delivery_addr = ", ".join(
        p for p in (delivery_parts.street_line, delivery_parts.bairro, delivery_parts.city_line) if p
    )
    delivery_differs = has_entrega and addresses_differ(dest_parts.compare_key, delivery_parts.compare_key)

    tp_emis = _text(ide, "tpEmis") or "1"
    emission_mode = _TP_EMIS_LABELS.get(tp_emis, f"tpEmis_{tp_emis}")
    auth = DanfeAuthorizationView(
        protocol=_text(prot, "nProt") if prot is not None else "",
        authorized_at=_text(prot, "dhRecbto") if prot is not None else "",
        c_stat=_text(prot, "cStat") if prot is not None else "",
        x_motivo=_text(prot, "xMotivo") if prot is not None else "",
        tp_emis=tp_emis,
        emission_mode=emission_mode,
        is_contingency=tp_emis != "1",
    )

    items: list[DanfeItemView] = []
    for det in _findall(root, "det"):
        prod = None
        imposto = None
        for ch in det:
            lt = _local(ch.tag)
            if lt == "prod":
                prod = ch
            elif lt == "imposto":
                imposto = ch
        if prod is None:
            continue
        icms_parent = None
        if imposto is not None:
            for ch in imposto:
                if _local(ch.tag) == "ICMS":
                    icms_parent = ch
                    break
        vbc, vicms, vbcst, vicmsst, picms = _icms_values(icms_parent)
        vipi, pipi = _ipi_value(imposto)
        ean = _valid_ean(_text(prod, "cEAN") or _text(prod, "cEANTrib"))
        item_trib = _text(imposto, "vTotTrib") if imposto is not None else ""
        items.append(
            DanfeItemView(
                line=_text(det, "nItem") or str(len(items) + 1),
                code=_text(prod, "cProd"),
                description=_text(prod, "xProd"),
                ean=ean,
                ncm=_text(prod, "NCM"),
                tax_classification=_tax_from_icms(icms_parent),
                cfop=_text(prod, "CFOP"),
                unit=_text(prod, "uCom"),
                quantity=_text(prod, "qCom"),
                unit_price=_text(prod, "vUnCom"),
                total=_text(prod, "vProd"),
                discount=_text(prod, "vDesc"),
                icms_base=vbc,
                icms_st_base=vbcst,
                icms_value=vicms,
                icms_st_value=vicmsst,
                ipi_value=vipi,
                icms_rate=picms,
                ipi_rate=pipi,
                approx_taxes=item_trib,
            )
        )

    transport = DanfeTransportView(
        freight_mod=_text(transp, "modFrete") if transp is not None else "9"
    )
    if transp is not None:
        t = None
        for ch in transp:
            if _local(ch.tag) == "transporta":
                t = ch
                break
        if t is not None:
            transport.carrier_name = _text(t, "xNome")
            transport.carrier_doc = _text(t, "CNPJ") or _text(t, "CPF")
            transport.carrier_ie = _text(t, "IE")
            transport.carrier_city = _text(t, "xMun")
            transport.carrier_uf = _text(t, "UF")
        vol = None
        for ch in transp:
            if _local(ch.tag) == "vol":
                vol = ch
                break
        if vol is not None:
            transport.volumes_qty = _text(vol, "qVol")
            transport.volumes_species = _text(vol, "esp")
            transport.volumes_brand = _text(vol, "marca")
            transport.volumes_number = _text(vol, "nVol")
            transport.gross_weight = _text(vol, "pesoB")
            transport.net_weight = _text(vol, "pesoL")
        veic = None
        for ch in transp:
            if _local(ch.tag) == "veicTransp":
                veic = ch
                break
        if veic is not None:
            transport.vehicle_plate = _text(veic, "placa")
            transport.vehicle_uf = _text(veic, "UF")

    dups: list[DanfeDuplicateView] = []
    if fat is not None:
        for dup in fat:
            if _local(dup.tag) == "dup":
                dups.append(
                    DanfeDuplicateView(
                        number=_text(dup, "nDup"),
                        due_date=_text(dup, "dVenc"),
                        amount=_text(dup, "vDup"),
                    )
                )

    totals = DanfeTotalsView(
        icms_base=_text(total, "vBC") or "0.00",
        icms_value=_text(total, "vICMS") or "0.00",
        icms_st_base=_text(total, "vBCST") or "0.00",
        icms_st_value=_text(total, "vST") or "0.00",
        products=_text(total, "vProd") or "0.00",
        freight=_text(total, "vFrete") or "0.00",
        insurance=_text(total, "vSeg") or "0.00",
        discount=_text(total, "vDesc") or "0.00",
        other=_text(total, "vOutro") or "0.00",
        ipi_value=_text(total, "vIPI") or "0.00",
        pis_value=_text(total, "vPIS") or "0.00",
        cofins_value=_text(total, "vCOFINS") or "0.00",
        total_nf=_text(total, "vNF") or "0.00",
        approx_taxes=_text(total, "vTotTrib") or "",
    )

    uf_hint = emit_uf.upper()
    consultation = _UF_CONSULTA_HINT.get(
        uf_hint,
        "Consulta de autenticidade no portal da NF-e ou SEFAZ autorizadora",
    )

    return DanfeViewModel(
        access_key=access,
        tp_nf=_text(ide, "tpNF") or "1",
        series=_text(ide, "serie"),
        number=_text(ide, "nNF"),
        nature=_text(ide, "natOp"),
        issue_date=_text(ide, "dhEmi") or _text(ide, "dEmi"),
        exit_date=_text(ide, "dhSaiEnt") or _text(ide, "dSaiEnt"),
        tp_amb=_text(ide, "tpAmb") or "2",
        emit_name=_text(emit, "xNome"),
        emit_fantasy=_text(emit, "xFant"),
        emit_cnpj=_text(emit, "CNPJ"),
        emit_ie=_text(emit, "IE"),
        emit_ie_st=_text(emit, "IEST"),
        emit_crt=_text(emit, "CRT"),
        emit_address=emit_addr,
        emit_address_line1=f"{emit_parts.street_line} - {emit_parts.bairro}".strip(" -"),
        emit_address_line2=emit_parts.city_line,
        emit_phone=emit_phone,
        emit_uf=emit_uf,
        dest_name=_text(dest, "xNome"),
        dest_doc=_text(dest, "CNPJ") or _text(dest, "CPF"),
        dest_ie=_text(dest, "IE"),
        dest_address=dest_addr,
        dest_address_parts=dest_parts,
        dest_phone=dest_phone,
        dest_uf=dest_uf,
        delivery_address=delivery_addr,
        delivery_name=delivery_name,
        delivery_doc=delivery_doc,
        delivery_ie=delivery_ie,
        delivery_address_parts=delivery_parts,
        has_entrega=has_entrega,
        delivery_differs_from_dest=delivery_differs,
        items=items,
        totals=totals,
        transport=transport,
        duplicates=dups,
        invoice_number_fat=_text(fat, "nFat") if fat is not None else "",
        invoice_value_fat=_text(fat, "vOrig") or _text(fat, "vLiq") if fat is not None else "",
        inf_cpl=_text(inf_adic, "infCpl") if inf_adic is not None else "",
        inf_ad_fisco=_text(inf_adic, "infAdFisco") if inf_adic is not None else "",
        authorization=auth,
        consultation_hint=consultation,
        cancelled=cancelled,
    )

