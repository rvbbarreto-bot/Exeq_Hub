"""Montagem NFC-e 4.00 (mod 65) — PDV presencial SP."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from xml.etree import ElementTree as ET

from integrations.sefaz_nfe.access_key import UF_IBGE_CODE, build_access_key
from integrations.sefaz_nfe.xml_nfe import (
    HOMOLOG_DEST_NAME,
    NFE_NS,
    _addr_part,
    _cmun,
    _crt,
    _digits,
    _el,
    _money_cents,
    _qty,
    _qty_str,
)
from apps.nfce.tax import map_csosn_to_xml_group

ET.register_namespace("", NFE_NS)


def build_nfce_xml(*, snapshot: dict[str, Any], access_key: str | None = None) -> bytes:
    emit = snapshot.get("emitente") or {}
    dest = snapshot.get("destinatario")
    header = snapshot.get("header") or {}
    items = snapshot.get("items") or []
    totals = snapshot.get("totals") or {}
    payment = snapshot.get("payment") or {}

    if not items:
        raise ValueError("snapshot sem itens para NFC-e")

    uf = (_addr_part(emit.get("address") or {}, "uf", "UF") or "SP").upper()
    issue_date = header.get("issue_date") or "2026-01-01"
    series = int(header.get("series") or 1)
    number = int(header.get("number") or 1)
    tp_amb = str(header.get("tp_amb") or "2")
    cnpj = _digits(emit.get("cnpj") or "", 14)
    omit_dest = header.get("omit_dest") in (True, "1", 1, "true") or dest is None

    if not access_key or len(str(access_key)) != 44 or not str(access_key).isdigit():
        access_key = build_access_key(
            uf=uf,
            issue_date_iso=issue_date,
            cnpj=cnpj,
            series=series,
            number=number,
            model="65",
        )

    nfe = ET.Element(f"{{{NFE_NS}}}NFe")
    inf = _el(nfe, "infNFe")
    inf.set("Id", f"NFe{access_key}")
    inf.set("versao", "4.00")

    ide = _el(inf, "ide")
    _el(ide, "cUF", UF_IBGE_CODE.get(uf, "35"))
    _el(ide, "cNF", access_key[35:43])
    _el(ide, "natOp", (header.get("nature") or "VENDA")[:60])
    _el(ide, "mod", "65")
    _el(ide, "serie", str(series))
    _el(ide, "nNF", str(number))
    dh_emi = (header.get("dh_emi") or "").strip()
    if not dh_emi:
        dh_emi = f"{issue_date}T12:00:00-03:00"
    _el(ide, "dhEmi", dh_emi)
    _el(ide, "tpNF", "1")
    _el(ide, "idDest", "1")
    _el(ide, "cMunFG", _cmun(emit.get("address") or {}))
    from apps.fiscal.rtc_goods import goods_rtc_mode, rtc_emit_xml_active

    if rtc_emit_xml_active(totals=totals, mode=goods_rtc_mode(document_model="65")):
        from integrations.sefaz_nfe.xml_rtc_ub import append_cmun_fg_ibs

        append_cmun_fg_ibs(ide, snapshot)
    _el(ide, "tpImp", "4")
    _el(ide, "tpEmis", "1")
    _el(ide, "cDV", access_key[-1])
    _el(ide, "tpAmb", tp_amb)
    _el(ide, "finNFe", "1")
    _el(ide, "indFinal", "1")
    _el(ide, "indPres", "1")
    _el(ide, "procEmi", "0")
    _el(ide, "verProc", "EXEQHubNFCe010")

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
    ie = "".join(ch for ch in str(emit.get("ie") or "") if ch.isalnum())
    _el(emit_el, "IE", ie if ie else "ISENTO")
    _el(emit_el, "CRT", _crt(str(emit.get("crt") or "")))

    if not omit_dest and isinstance(dest, dict):
        dest_el = _el(inf, "dest")
        raw_doc = dest.get("document") or ""
        _el(dest_el, "CPF", _digits(raw_doc, 11))
        if tp_amb == "2":
            _el(dest_el, "xNome", HOMOLOG_DEST_NAME[:60])
        else:
            _el(dest_el, "xNome", (dest.get("name") or "CONSUMIDOR")[:60])
        _el(dest_el, "indIEDest", "9")

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

        _el(prod, "cProd", str(it.get("code") or "PROD")[:60])
        _el(prod, "cEAN", "SEM GTIN")
        _el(prod, "xProd", str(it.get("description") or "PRODUTO")[:120])
        _el(prod, "NCM", str(it.get("ncm") or "00000000")[:8])
        _el(prod, "CFOP", str(it.get("cfop") or "5102")[:4])
        _el(prod, "uCom", str(it.get("unit") or "UN")[:6])
        _el(prod, "qCom", _qty_str(qty))
        _el(prod, "vUnCom", f"{v_un:.10f}")
        _el(prod, "vProd", f"{v_prod:.2f}")
        _el(prod, "cEANTrib", "SEM GTIN")
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

        for kind, tag in (("pis", "PIS"), ("cofins", "COFINS")):
            blk = taxes.get(kind) or {}
            parent = _el(imposto, tag)
            cst = str(blk.get("cst") or "07")[:2]
            if cst in ("04", "05", "06", "07", "08", "09"):
                g = _el(parent, f"{tag}NT")
                _el(g, "CST", cst)
            else:
                g = _el(parent, f"{tag}Aliq")
                _el(g, "CST", cst)
                _el(g, "vBC", _money_cents(int(blk.get("base_cents") or 0)))
                _el(g, "p" + tag, f"{Decimal(int(blk.get('rate_bp') or 0)) / Decimal(100):.4f}")
                _el(g, "v" + tag, _money_cents(int(blk.get("value_cents") or 0)))

        rtc = taxes.get("rtc") or {}
        if rtc.get("xml_ub"):
            from integrations.sefaz_nfe.xml_nfce_rtc import append_item_ibscbs

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
    _el(icmstot, "vFrete", "0.00")
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
    _el(icmstot, "vTotTrib", "0.00")

    rtc_totals = totals.get("rtc") if isinstance(totals.get("rtc"), dict) else None
    pay_cents = tot
    if rtc_totals:
        from integrations.sefaz_nfe.xml_nfce_rtc import append_total_ibscbs

        pay_cents = append_total_ibscbs(total_el, rtc_totals, v_nf_cents=tot)

    transp = _el(inf, "transp")
    _el(transp, "modFrete", "9")

    pag = _el(inf, "pag")
    detpag = _el(pag, "detPag")
    _el(detpag, "tPag", str(payment.get("method") or "99")[:2])
    _el(detpag, "vPag", _money_cents(int(payment.get("amount_cents") or pay_cents)))

    inf_adic = _el(inf, "infAdic")
    _el(inf_adic, "infCpl", "NFC-e gerada pelo EXEQ Hub (emissor proprio).")

    from integrations.sefaz_nfe.nfce_supplement import append_nfce_supplement

    sefaz_meta = snapshot.get("sefaz") if isinstance(snapshot.get("sefaz"), dict) else {}
    csc_id = str(header.get("csc_id") or sefaz_meta.get("csc_id") or "1")
    csc_token = str(header.get("csc_token") or sefaz_meta.get("csc_token") or "")
    qr_base = header.get("qr_base_url") or sefaz_meta.get("qr_base_url")

    append_nfce_supplement(
        nfe,
        access_key=str(access_key),
        tp_amb=tp_amb,
        total_cents=tot,
        csc_id=csc_id,
        csc_token=csc_token,
        qr_base_url=qr_base,
    )

    return ET.tostring(nfe, encoding="utf-8", xml_declaration=True)


def access_key_from_signed_or_snap(xml: bytes | None, snapshot: dict[str, Any]) -> str:
    if xml:
        try:
            from integrations.nfse.xml_safe import safe_fromstring

            root = safe_fromstring(xml)
            for el in root.iter():
                tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if tag == "infNFe":
                    rid = el.get("Id") or ""
                    if rid.startswith("NFe") and len(rid) == 47:
                        return rid[3:]
        except Exception:  # noqa: BLE001
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
        model="65",
    )
