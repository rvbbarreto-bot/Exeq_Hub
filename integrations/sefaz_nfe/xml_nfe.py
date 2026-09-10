"""Montagem NFe 4.00 a partir do fiscal_snapshot — happy path B2B SP (U3/I3)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from xml.etree import ElementTree as ET

from lxml import etree

from integrations.nfse.xml_safe import UnsafeXmlError, safe_fromstring
from apps.nfe.csosn import map_csosn_to_xml_group
from apps.nfe.ie_validation import normalize_emitter_ie_for_xml
from integrations.sefaz_nfe.prod_fields import prod_c_ean
from integrations.sefaz_nfe.access_key import UF_IBGE_CODE, build_access_key, check_digit_mod11

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
ET.register_namespace("", NFE_NS)

HOMOLOG_DEST_NAME = "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL"
XML_LAYOUT_NOTES = (
    "I3 happy path SP: SN CSOSN102 ou CST00 interno; modFrete 9; "
    "tpAmb=2 força xNome dest homolog; idDest por UF emit/dest."
)


def _el(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    node = ET.SubElement(parent, f"{{{NFE_NS}}}{tag}")
    if text is not None:
        node.text = text
    return node


def _money_cents(cents: int) -> str:
    return f"{Decimal(int(cents)) / Decimal(100):.2f}"


def _qty(val: str | Decimal | float) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _qty_str(q: Decimal) -> str:
    return f"{q:.4f}"


def _digits(doc: str, size: int) -> str:
    d = "".join(ch for ch in str(doc or "") if ch.isdigit())
    return d.zfill(size)[:size]


def _crt(tax_regime: str) -> str:
    if tax_regime == "simples_nacional":
        return "1"
    return "3"


def _cmun(addr: dict) -> str:
    raw = addr.get("codigo_ibge") or addr.get("codigo_municipio_ibge") or addr.get("ibge") or ""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())[:7]
    return digits if len(digits) == 7 else "3504107"


def _addr_part(addr: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = addr.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _id_dest(*, emit_uf: str, dest_uf: str) -> str:
    e = (emit_uf or "").upper().strip()
    d = (dest_uf or e).upper().strip()
    if d in {"EX", "EXTERIOR"}:
        return "3"
    return "1" if e == d else "2"


def build_nfe_xml(*, snapshot: dict[str, Any], access_key: str | None = None) -> bytes:
    """Gera NFe (infNFe) para SN CSOSN ou CST 00 — onda 1 SP."""
    emit = snapshot.get("emitente") or {}
    dest = snapshot.get("destinatario") or {}
    header = snapshot.get("header") or {}
    items = snapshot.get("items") or []
    totals = snapshot.get("totals") or {}
    payment = snapshot.get("payment") or {}

    if not items:
        raise ValueError("snapshot sem itens para NF-e")

    uf = (_addr_part(emit.get("address") or {}, "uf", "UF") or "SP").upper()
    daddr = dest.get("address") or {}
    duf = (_addr_part(daddr, "uf", "UF") or uf).upper()
    issue_date = header.get("issue_date") or "2026-01-01"
    series = int(header.get("series") or 1)
    number = int(header.get("number") or 1)
    tp_amb = str(header.get("tp_amb") or "2")
    cnpj = _digits(emit.get("cnpj") or "", 14)
    ind_final = "1" if header.get("consumer_final") in (True, "1", 1, "true") else "0"
    ind_ie_dest = str(header.get("ind_ie_dest") or dest.get("ind_ie_dest") or "9")[:1]
    id_dest = _id_dest(emit_uf=uf, dest_uf=duf)

    key_s = str(access_key or "")
    if len(key_s) == 44 and key_s.isdigit():
        if check_digit_mod11(key_s[:43]) != key_s[-1]:
            access_key = build_access_key(
                uf=uf,
                issue_date_iso=issue_date,
                cnpj=cnpj,
                series=series,
                number=number,
            )
    else:
        access_key = build_access_key(
            uf=uf,
            issue_date_iso=issue_date,
            cnpj=cnpj,
            series=series,
            number=number,
        )

    nfe = ET.Element(f"{{{NFE_NS}}}NFe")
    inf = _el(nfe, "infNFe")
    inf.set("Id", f"NFe{access_key}")
    inf.set("versao", "4.00")

    ide = _el(inf, "ide")
    _el(ide, "cUF", UF_IBGE_CODE.get(uf, "35"))
    _el(ide, "cNF", access_key[35:43])
    _el(ide, "natOp", (header.get("nature") or "VENDA")[:60])
    _el(ide, "mod", "55")
    _el(ide, "serie", str(series))
    _el(ide, "nNF", str(number))
    dh_emi = (header.get("dh_emi") or "").strip()
    if not dh_emi:
        dh_emi = f"{issue_date}T12:00:00-03:00"
    _el(ide, "dhEmi", dh_emi)
    exit_raw = (header.get("dh_sai_ent") or header.get("exit_date") or "").strip()
    if exit_raw:
        dh_sai = exit_raw if "T" in exit_raw else f"{exit_raw}T12:00:00-03:00"
        _el(ide, "dhSaiEnt", dh_sai)
    _el(ide, "tpNF", "1")
    _el(ide, "idDest", id_dest)
    _el(ide, "cMunFG", _cmun(emit.get("address") or {}))
    from apps.fiscal.rtc_goods import goods_rtc_mode, rtc_emit_xml_active

    if rtc_emit_xml_active(totals=totals, mode=goods_rtc_mode(document_model="55")):
        from integrations.sefaz_nfe.xml_rtc_ub import append_cmun_fg_ibs

        append_cmun_fg_ibs(ide, snapshot)
    _el(ide, "tpImp", "1")
    _el(ide, "tpEmis", "1")
    _el(ide, "cDV", access_key[-1])
    _el(ide, "tpAmb", tp_amb)
    _el(ide, "finNFe", str(header.get("finality") or "1")[:1])
    _el(ide, "indFinal", ind_final)
    _el(ide, "indPres", str(header.get("buyer_presence") or "9")[:1])
    _el(ide, "procEmi", "0")
    _el(ide, "verProc", "EXEQHubNFe010")

    emit_el = _el(inf, "emit")
    _el(emit_el, "CNPJ", cnpj)
    _el(emit_el, "xNome", (emit.get("name") or "EMITENTE")[:60])
    eaddr = emit.get("address") or {}
    ender = _el(emit_el, "enderEmit")
    _el(ender, "xLgr", _addr_part(eaddr, "logradouro", "street", default="RUA")[:60])
    _el(ender, "nro", _addr_part(eaddr, "numero", "number", default="S/N")[:60])
    _el(ender, "xBairro", _addr_part(eaddr, "bairro", "district", default="CENTRO")[:60])
    _el(ender, "cMun", _cmun(eaddr))
    _el(ender, "xMun", _addr_part(eaddr, "municipio", "city", default="MUNICIPIO")[:60])
    _el(ender, "UF", uf)
    cep = "".join(ch for ch in _addr_part(eaddr, "cep", "CEP") if ch.isdigit()).zfill(8)[:8]
    _el(ender, "CEP", cep if cep != "00000000" else "01001000")
    _el(ender, "cPais", "1058")
    _el(ender, "xPais", "BRASIL")
    if emit.get("phone"):
        _el(ender, "fone", str(emit["phone"])[:14])
    _el(emit_el, "IE", normalize_emitter_ie_for_xml(str(emit.get("ie") or ""), tp_amb=tp_amb))
    _el(emit_el, "CRT", _crt(str(emit.get("crt") or "")))

    dest_el = _el(inf, "dest")
    dtype = (dest.get("document_type") or "").lower()
    raw_doc = dest.get("document") or ""
    digs = "".join(ch for ch in str(raw_doc) if ch.isdigit())
    if dtype == "cnpj" or len(digs) == 14:
        _el(dest_el, "CNPJ", _digits(raw_doc, 14))
    else:
        _el(dest_el, "CPF", _digits(raw_doc, 11))
    if tp_amb == "2":
        _el(dest_el, "xNome", HOMOLOG_DEST_NAME[:60])
    else:
        _el(dest_el, "xNome", (dest.get("name") or "DESTINATARIO")[:60])
    dender = _el(dest_el, "enderDest")
    _el(dender, "xLgr", _addr_part(daddr, "logradouro", "street", default="RUA")[:60])
    _el(dender, "nro", _addr_part(daddr, "numero", "number", default="S/N")[:60])
    _el(dender, "xBairro", _addr_part(daddr, "bairro", "district", default="CENTRO")[:60])
    _el(dender, "cMun", _cmun(daddr))
    _el(dender, "xMun", _addr_part(daddr, "municipio", "city", default="MUNICIPIO")[:60])
    _el(dender, "UF", duf)
    dcep = "".join(ch for ch in _addr_part(daddr, "cep", "CEP") if ch.isdigit()).zfill(8)[:8]
    _el(dender, "CEP", dcep if dcep != "00000000" else "01001000")
    _el(dender, "cPais", "1058")
    _el(dender, "xPais", "BRASIL")
    _el(dest_el, "indIEDest", ind_ie_dest)
    if ind_ie_dest == "1":
        dest_ie = "".join(
            ch
            for ch in str(
                daddr.get("ie") or daddr.get("state_registration") or dest.get("ie") or ""
            )
            if ch.isalnum()
        )
        if dest_ie:
            _el(dest_el, "IE", dest_ie)

    entrega_snap = snapshot.get("entrega")
    if entrega_snap:
        ent_el = _el(inf, "entrega")
        eaddr = entrega_snap.get("address") or entrega_snap
        doc = entrega_snap.get("document") or entrega_snap.get("cnpj") or entrega_snap.get("cpf")
        if doc:
            digs = "".join(ch for ch in str(doc) if ch.isdigit())
            if len(digs) == 14:
                _el(ent_el, "CNPJ", digs.zfill(14)[:14])
            elif len(digs) == 11:
                _el(ent_el, "CPF", digs.zfill(11)[:11])
        _el(ent_el, "xLgr", _addr_part(eaddr, "logradouro", "street", default="RUA")[:60])
        _el(ent_el, "nro", _addr_part(eaddr, "numero", "number", default="S/N")[:60])
        cpl = _addr_part(eaddr, "complemento", "xCpl", default="")
        if cpl:
            _el(ent_el, "xCpl", cpl[:60])
        _el(ent_el, "xBairro", _addr_part(eaddr, "bairro", "district", default="CENTRO")[:60])
        _el(ent_el, "cMun", _cmun(eaddr))
        _el(ent_el, "xMun", _addr_part(eaddr, "municipio", "city", default="MUNICIPIO")[:60])
        euf = _addr_part(eaddr, "uf", "UF", default=uf).upper()[:2]
        _el(ent_el, "UF", euf)
        ecep = "".join(ch for ch in _addr_part(eaddr, "cep", "CEP") if ch.isdigit()).zfill(8)[:8]
        _el(ent_el, "CEP", ecep if ecep != "00000000" else "01001000")

    products_cents = 0
    for it in items:
        det = _el(inf, "det")
        det.set("nItem", str(it.get("line") or 1))
        prod = _el(det, "prod")
        qty = _qty(it.get("quantity") or "1")
        unit_cents = int(it.get("unit_price_cents") or 0)
        line_cents = int(it.get("total_cents") or 0)
        if line_cents <= 0 and unit_cents > 0:
            line_cents = int((qty * Decimal(unit_cents)).quantize(Decimal("1")))
        products_cents += line_cents
        v_prod = Decimal(line_cents) / Decimal(100)
        v_un = (v_prod / qty) if qty > 0 else Decimal(unit_cents) / Decimal(100)
        v_un = v_un.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)

        ean = prod_c_ean(it)
        _el(prod, "cProd", str(it.get("code") or "PROD")[:60])
        _el(prod, "cEAN", ean)
        _el(prod, "xProd", str(it.get("description") or "PRODUTO")[:120])
        _el(prod, "NCM", str(it.get("ncm") or "00000000")[:8])
        _el(prod, "CFOP", str(it.get("cfop") or "5102")[:4])
        _el(prod, "uCom", str(it.get("unit") or "UN")[:6])
        _el(prod, "qCom", _qty_str(qty))
        _el(prod, "vUnCom", f"{v_un:.10f}")
        _el(prod, "vProd", f"{v_prod:.2f}")
        _el(prod, "cEANTrib", ean)
        _el(prod, "uTrib", str(it.get("unit") or "UN")[:6])
        _el(prod, "qTrib", _qty_str(qty))
        _el(prod, "vUnTrib", f"{v_un:.10f}")
        _el(prod, "indTot", "1")

        imposto = _el(det, "imposto")
        taxes = it.get("taxes") or {}
        icms_block = taxes.get("icms") or {}
        icms = _el(imposto, "ICMS")
        origin = str(it.get("origin") or taxes.get("origin") or "0")[:1]
        is_sn = (
            icms_block.get("regime") == "sn"
            or bool(str(icms_block.get("csosn") or it.get("csosn") or "").strip())
        )
        if is_sn:
            csosn = str(icms_block.get("csosn") or it.get("csosn") or "102").zfill(3)
            grp_name = icms_block.get("xml_group") or map_csosn_to_xml_group(csosn)
            grp = _el(icms, grp_name)
            _el(grp, "orig", origin)
            _el(grp, "CSOSN", csosn)
        else:
            grp = _el(icms, "ICMS00")
            _el(grp, "orig", origin)
            _el(grp, "CST", str(icms_block.get("cst") or it.get("icms_cst") or "00").zfill(2))
            _el(grp, "modBC", "3")
            _el(grp, "vBC", _money_cents(int(icms_block.get("base_cents") or line_cents)))
            rate_bp = int(icms_block.get("rate_bp") or 0)
            _el(grp, "pICMS", f"{Decimal(rate_bp) / Decimal(100):.4f}")
            _el(grp, "vICMS", _money_cents(int(icms_block.get("value_cents") or 0)))

        default_pc_cst = "49" if is_sn else "07"
        for kind, tag in (("pis", "PIS"), ("cofins", "COFINS")):
            blk = taxes.get(kind) or {}
            parent = _el(imposto, tag)
            cst = str(blk.get("cst") or default_pc_cst)[:2]
            if is_sn and cst in ("01", "02", "03"):
                cst = "49"
            if cst in ("04", "05", "06", "07", "08", "09"):
                g = _el(parent, f"{tag}NT")
                _el(g, "CST", cst)
            elif cst in ("49", "99"):
                g = _el(parent, f"{tag}Outr")
                _el(g, "CST", cst)
                base = int(blk.get("base_cents") or 0)
                rate = int(blk.get("rate_bp") or 0)
                value = int(blk.get("value_cents") or 0)
                if base or rate or value:
                    _el(g, "vBC", _money_cents(base))
                    _el(g, "p" + tag, f"{Decimal(rate) / Decimal(100):.4f}")
                    _el(g, "v" + tag, _money_cents(value))
            else:
                g = _el(parent, f"{tag}Aliq")
                _el(g, "CST", cst)
                _el(g, "vBC", _money_cents(int(blk.get("base_cents") or 0)))
                _el(g, "p" + tag, f"{Decimal(int(blk.get('rate_bp') or 0)) / Decimal(100):.4f}")
                _el(g, "v" + tag, _money_cents(int(blk.get("value_cents") or 0)))

        item_trib = taxes.get("v_tot_trib_cents")
        if item_trib:
            _el(imposto, "vTotTrib", _money_cents(int(item_trib)))

        rtc = taxes.get("rtc") or {}
        if rtc.get("xml_ub"):
            from integrations.sefaz_nfe.xml_nfe_rtc import append_item_ibscbs

            append_item_ibscbs(imposto, rtc)

    if int(totals.get("products_cents") or 0) > 0:
        products_cents = int(totals["products_cents"])

    total_el = _el(inf, "total")
    icmstot = _el(total_el, "ICMSTot")
    _el(icmstot, "vBC", _money_cents(int(totals.get("icms_base_cents") or 0)))
    _el(icmstot, "vICMS", _money_cents(int(totals.get("icms_cents") or 0)))
    _el(icmstot, "vICMSDeson", "0.00")
    _el(icmstot, "vFCP", "0.00")
    _el(icmstot, "vBCST", "0.00")
    _el(icmstot, "vST", "0.00")
    _el(icmstot, "vFCPST", "0.00")
    _el(icmstot, "vFCPSTRet", "0.00")
    _el(icmstot, "vProd", _money_cents(products_cents))
    _el(icmstot, "vFrete", _money_cents(int(totals.get("freight_cents") or 0)))
    _el(icmstot, "vSeg", "0.00")
    _el(icmstot, "vDesc", _money_cents(int(totals.get("discount_cents") or 0)))
    _el(icmstot, "vII", "0.00")
    _el(icmstot, "vIPI", "0.00")
    _el(icmstot, "vIPIDevol", "0.00")
    _el(icmstot, "vPIS", _money_cents(int(totals.get("pis_cents") or 0)))
    _el(icmstot, "vCOFINS", _money_cents(int(totals.get("cofins_cents") or 0)))
    _el(icmstot, "vOutro", "0.00")
    tot = int(totals.get("total_cents") or products_cents)
    _el(icmstot, "vNF", _money_cents(tot))
    _el(icmstot, "vTotTrib", _money_cents(int(totals.get("v_tot_trib_cents") or 0)))

    rtc_totals = totals.get("rtc") if isinstance(totals.get("rtc"), dict) else None
    pay_cents = tot
    if rtc_totals:
        from integrations.sefaz_nfe.xml_nfe_rtc import append_total_ibscbs

        pay_cents = append_total_ibscbs(total_el, rtc_totals, v_nf_cents=tot)

    billing = snapshot.get("billing") or {}
    if billing:
        fat = _el(inf, "fat")
        if billing.get("nFat"):
            _el(fat, "nFat", str(billing["nFat"])[:60])
        if billing.get("vOrig"):
            _el(fat, "vOrig", str(billing["vOrig"]))
        if billing.get("vLiq"):
            _el(fat, "vLiq", str(billing["vLiq"]))
        for dup in billing.get("duplicates") or []:
            if not isinstance(dup, dict):
                continue
            dup_el = _el(fat, "dup")
            if dup.get("nDup"):
                _el(dup_el, "nDup", str(dup["nDup"])[:60])
            if dup.get("dVenc"):
                _el(dup_el, "dVenc", str(dup["dVenc"])[:10])
            if dup.get("vDup"):
                _el(dup_el, "vDup", str(dup["vDup"]))

    transp = _el(inf, "transp")
    freight_mod = str(
        (snapshot.get("transport") or {}).get("modFrete")
        or header.get("freight_mod")
        or "9"
    )[:1]
    _el(transp, "modFrete", freight_mod)
    transport = snapshot.get("transport") or {}
    carrier = transport.get("carrier") or {}
    if carrier:
        t = _el(transp, "transporta")
        doc = "".join(ch for ch in str(carrier.get("document") or "") if ch.isdigit())
        if len(doc) == 14:
            _el(t, "CNPJ", _digits(doc, 14))
        elif len(doc) == 11:
            _el(t, "CPF", _digits(doc, 11))
        if carrier.get("name"):
            _el(t, "xNome", str(carrier["name"])[:60])
        if carrier.get("ie"):
            _el(t, "IE", "".join(ch for ch in str(carrier["ie"]) if ch.isalnum()))
        if carrier.get("city"):
            _el(t, "xMun", str(carrier["city"])[:60])
        if carrier.get("uf"):
            _el(t, "UF", str(carrier["uf"])[:2])
    vol = transport.get("volume") or {}
    if vol:
        v = _el(transp, "vol")
        if vol.get("qVol"):
            _el(v, "qVol", str(vol["qVol"])[:15])
        if vol.get("esp"):
            _el(v, "esp", str(vol["esp"])[:60])
        if vol.get("marca"):
            _el(v, "marca", str(vol["marca"])[:60])
        if vol.get("pesoB"):
            _el(v, "pesoB", str(vol["pesoB"]))
        if vol.get("pesoL"):
            _el(v, "pesoL", str(vol["pesoL"]))
    veic = transport.get("vehicle") or {}
    if veic:
        ve = _el(transp, "veicTransp")
        if veic.get("placa"):
            _el(ve, "placa", str(veic["placa"])[:8])
        if veic.get("uf"):
            _el(ve, "UF", str(veic["uf"])[:2])

    pag = _el(inf, "pag")
    detpag = _el(pag, "detPag")
    _el(detpag, "tPag", str(payment.get("method") or "99")[:2])
    _el(detpag, "vPag", _money_cents(int(payment.get("amount_cents") or pay_cents)))

    inf_adic = _el(inf, "infAdic")
    inf_cpl = (snapshot.get("inf_adic") or {}).get("infCpl") or "NF-e gerada pelo EXEQ Hub (emissor proprio)."
    _el(inf_adic, "infCpl", str(inf_cpl)[:5000])
    inf_fisco = (snapshot.get("inf_adic") or {}).get("infAdFisco")
    if inf_fisco:
        _el(inf_adic, "infAdFisco", str(inf_fisco)[:2000])

    return ET.tostring(nfe, encoding="utf-8", xml_declaration=True)


def access_key_from_signed_or_snap(xml: bytes | None, snapshot: dict[str, Any]) -> str:
    if xml:
        try:
            root = safe_fromstring(xml)
            for el in root.iter():
                tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if tag == "infNFe":
                    rid = el.get("Id") or ""
                    if rid.startswith("NFe") and len(rid) == 47:
                        return rid[3:]
        except (etree.XMLSyntaxError, UnsafeXmlError, ValueError):
            pass
    header = snapshot.get("header") or {}
    emit = snapshot.get("emitente") or {}
    uf = (_addr_part(emit.get("address") or {}, "uf", "UF") or "SP").upper()
    return build_access_key(
        uf=uf,
        issue_date_iso=header.get("issue_date") or "2026-01-01",
        cnpj=emit.get("cnpj") or "",
        series=int(header.get("series") or 1),
        number=int(header.get("number") or 1),
    )
