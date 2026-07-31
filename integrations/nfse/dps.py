"""Mapper DPS Nacional (XML) a partir de NfIssue / dict — RF-10."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from lxml import etree

from apps.issuance.models import NfIssue
from apps.master_data.models import Customer, TaxRegime
from integrations.nfse.dps_contract import DpsContractError, assert_dps_structure

NFSE_NS = "http://www.sped.fazenda.gov.br/nfse"
DPS_VERSAO = "1.01"
VER_APLIC = "EXEQHUB_1.0"
TZ_BR = ZoneInfo("America/Sao_Paulo")


class DpsBuildError(ValueError):
    pass


def build_dps_id(
    *,
    c_loc_emi: str,
    prestador_doc: str,
    is_cpf: bool,
    serie: str | int,
    n_dps: str | int,
) -> str:
    """Id = DPS + mun(7) + tpInsc(1) + insc(14|11) + serie(5) + nDPS(15)."""
    cmun = _digits(c_loc_emi).zfill(7)[-7:]
    tp = "1" if is_cpf else "2"
    insc = _digits(prestador_doc)
    insc = insc.zfill(11 if is_cpf else 14)[-(11 if is_cpf else 14) :]
    serie_p = str(int(str(serie))).zfill(5)[-5:]
    n_pad = str(int(str(n_dps))).zfill(15)[-15:]
    return f"DPS{cmun}{tp}{insc}{serie_p}{n_pad}"


def to_sefin_dps_dict(
    issue: NfIssue,
    *,
    tp_amb: int = 2,
    serie: str | int = 1,
    n_dps: str | int | None = None,
    dh_emi: datetime | None = None,
    ver_aplic: str = VER_APLIC,
) -> dict[str, Any]:
    """Monta payload estruturado (espelho do layout DPS 1.01) a partir da NfIssue."""
    provider = issue.provider
    customer = issue.customer
    service = issue.service
    params = issue.resolved_params or {}

    if n_dps is None:
        # Usa parte numérica do UUID da nota (estável o bastante para lab).
        n_dps = int(str(issue.id).replace("-", "")[:15], 16) % (10**15) or 1

    amount = (Decimal(issue.amount_cents) / Decimal(100)).quantize(Decimal("0.01"))
    codigo_trib = (
        params.get("codigo_tributacao_nacional_iss")
        or service.codigo_tributacao_nacional_iss
        or service.lc116_item
        or service.service_code
    )
    raw_code = str(codigo_trib or "").strip()
    if "." in raw_code and raw_code.replace(".", "").isdigit():
        # LC 116 "1.01" / "17.01" → cTribNac 6 dígitos "010101" / "170101"
        parts = [p for p in raw_code.split(".") if p.isdigit()]
        if len(parts) >= 2:
            codigo_trib = f"{int(parts[0]):02d}{int(parts[1]):02d}01"[:6]
        else:
            codigo_trib = "".join(ch for ch in raw_code if ch.isdigit())
    else:
        codigo_trib = "".join(ch for ch in raw_code if ch.isdigit())
    if len(codigo_trib) != 6:
        raise DpsBuildError("cTribNac deve ter 6 dígitos (código nacional)")

    iss_retained = bool(params.get("iss_retained", False))
    tipo_retencao = int(params.get("tipo_retencao_iss") or (2 if iss_retained else 1))
    op_simp = 3 if provider.tax_regime == TaxRegime.SIMPLES else 1
    trib_issqn = int(params.get("tributacao_iss") or 1)
    reg_esp = int(
        params.get("regime_especial_tributacao")
        if params.get("regime_especial_tributacao") is not None
        else 0
    )

    now = dh_emi or datetime.now(TZ_BR)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_BR)

    c_loc = _digits(issue.ibge_code).zfill(7)
    prest_doc = _digits(provider.document)
    dps_id = build_dps_id(
        c_loc_emi=c_loc,
        prestador_doc=prest_doc,
        is_cpf=False,
        serie=serie,
        n_dps=n_dps,
    )

    prest: dict[str, Any] = {
        "CNPJ": prest_doc,
        "regTrib": {
            "opSimpNac": op_simp,
            "regEspTrib": reg_esp,
        },
    }
    if op_simp == 3:
        # 1 = Regime de apuração SN (ME/EPP) — alinhado Focus nfsen
        prest["regTrib"]["regApTribSN"] = int(
            params.get("regime_tributario_simples_nacional") or 1
        )
    # IM só se explicitamente solicitado (Atibaia/SEFIN E0120)
    if params.get("enviar_im_prestador") and provider.municipal_registration:
        prest["IM"] = str(provider.municipal_registration)

    toma = _tomador_dps(customer, fallback_ibge=issue.ibge_code)

    trib: dict[str, Any] = {
        "tribMun": {
            "tribISSQN": trib_issqn,
            "tpRetISSQN": tipo_retencao,
        }
    }
    if op_simp == 3:
        trib["totTrib"] = {
            "pTotTribSN": f"{Decimal(str(params.get('percentual_total_tributos_simples_nacional') or '6.0')).quantize(Decimal('0.01'))}"
        }
    else:
        trib["totTrib"] = {"indTotTrib": str(params.get("indicador_total_tributacao") or "0")}

    return {
        "infDPS": {
            "Id": dps_id,
            "tpAmb": int(tp_amb),
            "dhEmi": now.isoformat(timespec="seconds"),
            "verAplic": ver_aplic,
            "serie": str(int(str(serie))),
            "nDPS": str(int(str(n_dps))),
            "dCompet": issue.competence_date.isoformat(),
            "tpEmit": 1,
            "cLocEmi": c_loc,
            "prest": prest,
            "toma": toma,
            "serv": {
                "locPrest": {"cLocPrestacao": c_loc},
                "cServ": {
                    "cTribNac": codigo_trib[:6].zfill(6),
                    "xDescServ": (service.description or "Servico")[:2000],
                },
            },
            "valores": {
                "vServPrest": {"vServ": f"{amount}"},
                "trib": trib,
            },
        }
    }


def build_dps_xml_from_dict(payload: dict[str, Any]) -> bytes:
    """Serializa dict → XML DPS (namespace NFSe)."""
    inf = payload.get("infDPS") or payload
    prest = inf.get("prest") or {}
    cnpj = _digits(str(prest.get("CNPJ") or ""))
    cpf = _digits(str(prest.get("CPF") or ""))
    if not cnpj and not cpf:
        raise DpsBuildError("prest.CNPJ ou prest.CPF obrigatório")

    dps_id = inf.get("Id") or build_dps_id(
        c_loc_emi=str(inf.get("cLocEmi") or ""),
        prestador_doc=cnpj or cpf,
        is_cpf=bool(cpf and not cnpj),
        serie=str(inf.get("serie") or "1"),
        n_dps=str(inf.get("nDPS") or "1"),
    )

    root = etree.Element(f"{{{NFSE_NS}}}DPS", nsmap={None: NFSE_NS})
    root.set("versao", DPS_VERSAO)
    inf_el = etree.SubElement(root, f"{{{NFSE_NS}}}infDPS")
    inf_el.set("Id", dps_id)

    _txt(inf_el, "tpAmb", str(inf.get("tpAmb") or "2"))
    _txt(inf_el, "dhEmi", str(inf["dhEmi"]))
    if inf.get("verAplic"):
        _txt(inf_el, "verAplic", str(inf["verAplic"]))
    _txt(inf_el, "serie", str(inf["serie"]))
    _txt(inf_el, "nDPS", str(inf["nDPS"]))
    _txt(inf_el, "dCompet", str(inf["dCompet"]))
    _txt(inf_el, "tpEmit", str(inf.get("tpEmit") or "1"))
    _txt(inf_el, "cLocEmi", str(inf["cLocEmi"]).zfill(7))

    _append_prest(inf_el, prest)
    if inf.get("toma"):
        _append_toma(inf_el, inf["toma"])
    _append_serv(inf_el, inf["serv"])
    _append_valores(inf_el, inf["valores"])

    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
    try:
        assert_dps_structure(xml)
    except DpsContractError as exc:
        raise DpsBuildError(str(exc)) from exc
    return xml


def to_sefin_dps_xml(
    issue: NfIssue,
    *,
    tp_amb: int = 2,
    serie: str | int = 1,
    n_dps: str | int | None = None,
    dh_emi: datetime | None = None,
) -> bytes:
    """RF-10: NfIssue → XML DPS (ainda sem assinatura)."""
    return build_dps_xml_from_dict(
        to_sefin_dps_dict(
            issue, tp_amb=tp_amb, serie=serie, n_dps=n_dps, dh_emi=dh_emi
        )
    )


def _tomador_dps(customer: Customer, *, fallback_ibge: str) -> dict[str, Any]:
    toma: dict[str, Any] = {"xNome": customer.name}
    if customer.document_type == Customer.DocumentType.CPF:
        toma["CPF"] = _digits(customer.document)
    else:
        toma["CNPJ"] = _digits(customer.document)
    if customer.email:
        toma["email"] = customer.email

    addr = customer.address or {}
    cmun = _digits(
        str(
            addr.get("codigo_municipio")
            or addr.get("codigo_municipio_ibge")
            or addr.get("ibge_code")
            or fallback_ibge
        )
    ).zfill(7)
    cep = _digits(str(addr.get("cep") or addr.get("zip") or ""))
    end: dict[str, Any] = {"endNac": {"cMun": cmun}}
    if cep:
        end["endNac"]["CEP"] = cep.zfill(8)[-8:]
    if addr.get("logradouro") or addr.get("street"):
        end["xLgr"] = str(addr.get("logradouro") or addr.get("street"))
    if addr.get("numero") or addr.get("number"):
        end["nro"] = str(addr.get("numero") or addr.get("number"))
    if addr.get("complemento"):
        end["xCpl"] = str(addr["complemento"])
    if addr.get("bairro"):
        end["xBairro"] = str(addr["bairro"])
    toma["end"] = end
    return toma


def _append_prest(parent: etree._Element, prest: dict[str, Any]) -> None:
    el = etree.SubElement(parent, f"{{{NFSE_NS}}}prest")
    if prest.get("CPF"):
        _txt(el, "CPF", _digits(str(prest["CPF"])))
    else:
        _txt(el, "CNPJ", _digits(str(prest["CNPJ"])))
    if prest.get("IM"):
        _txt(el, "IM", str(prest["IM"]))
    if prest.get("email"):
        _txt(el, "email", str(prest["email"]))
    reg = prest.get("regTrib") or {}
    reg_el = etree.SubElement(el, f"{{{NFSE_NS}}}regTrib")
    _txt(reg_el, "opSimpNac", str(reg.get("opSimpNac") or "1"))
    if reg.get("regApTribSN") is not None:
        _txt(reg_el, "regApTribSN", str(reg["regApTribSN"]))
    _txt(reg_el, "regEspTrib", str(reg.get("regEspTrib") or "0"))


def _append_toma(parent: etree._Element, toma: dict[str, Any]) -> None:
    el = etree.SubElement(parent, f"{{{NFSE_NS}}}toma")
    if toma.get("CPF"):
        _txt(el, "CPF", _digits(str(toma["CPF"])))
    elif toma.get("CNPJ"):
        _txt(el, "CNPJ", _digits(str(toma["CNPJ"])))
    if toma.get("xNome"):
        _txt(el, "xNome", str(toma["xNome"]))
    end = toma.get("end")
    if end:
        end_el = etree.SubElement(el, f"{{{NFSE_NS}}}end")
        end_nac = end.get("endNac") or {}
        if end_nac:
            end_nac_el = etree.SubElement(end_el, f"{{{NFSE_NS}}}endNac")
            if end_nac.get("cMun"):
                _txt(end_nac_el, "cMun", str(end_nac["cMun"]).zfill(7))
            if end_nac.get("CEP"):
                _txt(end_nac_el, "CEP", _digits(str(end_nac["CEP"])).zfill(8)[-8:])
        for field in ("xLgr", "nro", "xCpl", "xBairro"):
            if end.get(field):
                _txt(end_el, field, str(end[field]))
    if toma.get("email"):
        _txt(el, "email", str(toma["email"]))


def _append_serv(parent: etree._Element, serv: dict[str, Any]) -> None:
    el = etree.SubElement(parent, f"{{{NFSE_NS}}}serv")
    loc = serv.get("locPrest") or {}
    loc_el = etree.SubElement(el, f"{{{NFSE_NS}}}locPrest")
    _txt(loc_el, "cLocPrestacao", str(loc.get("cLocPrestacao") or "").zfill(7))
    c_serv = serv.get("cServ") or {}
    c_el = etree.SubElement(el, f"{{{NFSE_NS}}}cServ")
    _txt(c_el, "cTribNac", str(c_serv.get("cTribNac") or ""))
    if c_serv.get("cTribMun"):
        _txt(c_el, "cTribMun", str(c_serv["cTribMun"]))
    _txt(c_el, "xDescServ", str(c_serv.get("xDescServ") or "Servico"))


def _append_valores(parent: etree._Element, valores: dict[str, Any]) -> None:
    el = etree.SubElement(parent, f"{{{NFSE_NS}}}valores")
    vsp = valores.get("vServPrest") or {}
    vsp_el = etree.SubElement(el, f"{{{NFSE_NS}}}vServPrest")
    _txt(vsp_el, "vServ", str(vsp.get("vServ") or "0.00"))
    trib = valores.get("trib") or {}
    trib_el = etree.SubElement(el, f"{{{NFSE_NS}}}trib")
    trib_mun = trib.get("tribMun") or {}
    tm_el = etree.SubElement(trib_el, f"{{{NFSE_NS}}}tribMun")
    _txt(tm_el, "tribISSQN", str(trib_mun.get("tribISSQN") or "1"))
    _txt(tm_el, "tpRetISSQN", str(trib_mun.get("tpRetISSQN") or "1"))
    if trib_mun.get("pAliq") is not None:
        _txt(tm_el, "pAliq", str(trib_mun["pAliq"]))
    tot = trib.get("totTrib")
    if tot:
        tot_el = etree.SubElement(trib_el, f"{{{NFSE_NS}}}totTrib")
        if tot.get("pTotTribSN") is not None:
            _txt(tot_el, "pTotTribSN", str(tot["pTotTribSN"]))
        if tot.get("indTotTrib") is not None:
            _txt(tot_el, "indTotTrib", str(tot["indTotTrib"]))
        vtot = tot.get("vTotTrib")
        if vtot:
            vt_el = etree.SubElement(tot_el, f"{{{NFSE_NS}}}vTotTrib")
            for field in ("vTotTribFed", "vTotTribEst", "vTotTribMun"):
                if vtot.get(field) is not None:
                    _txt(vt_el, field, str(vtot[field]))


def _txt(parent: etree._Element, name: str, value: str) -> None:
    el = etree.SubElement(parent, f"{{{NFSE_NS}}}{name}")
    el.text = value


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())
