"""XML InutNFe 4.00 — inutilização de faixa de numeração (U15)."""

from __future__ import annotations

from typing import Any

from lxml import etree

from integrations.sefaz_nfe.access_key import UF_IBGE_CODE

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
VER_INUT = "4.00"
MOD_NFE = "55"


class NfeInutBuildError(ValueError):
    pass


def _txt(parent: etree._Element, tag: str, value: str) -> etree._Element:
    el = etree.SubElement(parent, f"{{{NFE_NS}}}{tag}")
    el.text = value
    return el


def build_inf_inut_id(
    *,
    c_uf: str,
    ano: str,
    cnpj: str,
    series: int,
    n_ini: int,
    n_fin: int,
    modelo: str = MOD_NFE,
) -> str:
    """Id = ID + cUF(2) + AA(2) + CNPJ(14) + mod(2) + serie(3) + nIni(9) + nFin(9)."""
    cuf = "".join(c for c in str(c_uf) if c.isdigit()).zfill(2)[-2:]
    aa = "".join(c for c in str(ano) if c.isdigit()).zfill(2)[-2:]
    cnpj_d = "".join(c for c in str(cnpj) if c.isdigit())
    mod = "".join(c for c in str(modelo) if c.isdigit()).zfill(2)[-2:]
    if len(cnpj_d) != 14:
        raise NfeInutBuildError("CNPJ inválido para Id infInut")
    ser = str(max(1, int(series))).zfill(3)[-3:]
    ini = str(max(1, int(n_ini))).zfill(9)[-9:]
    fin = str(max(1, int(n_fin))).zfill(9)[-9:]
    return f"ID{cuf}{aa}{cnpj_d}{mod}{ser}{ini}{fin}"


def build_inut_nfe_xml(
    *,
    cnpj: str,
    uf: str,
    ano: str | int,
    series: int,
    n_ini: int,
    n_fin: int,
    x_just: str,
    tp_amb: str = "2",
    modelo: str = MOD_NFE,
) -> bytes:
    """Monta inutNFe/infInut sem Signature."""
    cnpj_d = "".join(c for c in str(cnpj or "") if c.isdigit())
    if len(cnpj_d) != 14:
        raise NfeInutBuildError("CNPJ emitente inválido")
    just = (x_just or "").strip()
    if not (15 <= len(just) <= 255):
        raise NfeInutBuildError("xJust deve ter entre 15 e 255 caracteres")
    ini = int(n_ini)
    fin = int(n_fin)
    if ini < 1 or fin < 1 or fin < ini:
        raise NfeInutBuildError("faixa nNFIni/nNFFin inválida")
    if fin - ini + 1 > 10_000:
        raise NfeInutBuildError("faixa máxima 10000 números por pedido")
    ser = max(1, int(series or 1))
    amb = str(tp_amb or "2").strip()[:1] or "2"
    uf_code = (uf or "SP").upper().strip()
    c_uf = UF_IBGE_CODE.get(uf_code) or (
        uf_code if uf_code.isdigit() and len(uf_code) == 2 else "35"
    )
    aa = "".join(c for c in str(ano) if c.isdigit())
    if len(aa) == 4:
        aa = aa[-2:]
    aa = aa.zfill(2)[-2:]

    inf_id = build_inf_inut_id(
        c_uf=c_uf,
        ano=aa,
        cnpj=cnpj_d,
        series=ser,
        n_ini=ini,
        n_fin=fin,
        modelo=modelo,
    )

    root = etree.Element(f"{{{NFE_NS}}}inutNFe", nsmap={None: NFE_NS}, versao=VER_INUT)
    inf = etree.SubElement(root, f"{{{NFE_NS}}}infInut", Id=inf_id)
    _txt(inf, "tpAmb", amb)
    _txt(inf, "xServ", "INUTILIZAR")
    _txt(inf, "cUF", c_uf)
    _txt(inf, "ano", aa)
    _txt(inf, "CNPJ", cnpj_d)
    _txt(inf, "mod", modelo)
    _txt(inf, "serie", str(ser))
    _txt(inf, "nNFIni", str(ini))
    _txt(inf, "nNFFin", str(fin))
    _txt(inf, "xJust", just)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def build_inut_from_context(
    *,
    n_ini: int,
    n_fin: int,
    x_just: str,
    context: dict[str, Any] | None = None,
) -> bytes:
    ctx = context or {}
    return build_inut_nfe_xml(
        cnpj=str(ctx.get("cnpj") or ""),
        uf=str(ctx.get("uf") or "SP"),
        ano=ctx.get("ano") or "",
        series=int(ctx.get("series") or 1),
        n_ini=n_ini,
        n_fin=n_fin,
        x_just=x_just,
        tp_amb=str(ctx.get("tp_amb") or "2"),
    )
