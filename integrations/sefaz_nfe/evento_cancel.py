"""Evento de cancelamento NF-e 110111 (Manual MOC) — I6."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from lxml import etree

from integrations.sefaz_nfe.access_key import UF_IBGE_CODE

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
TP_EVENTO_CANCEL = "110111"
VER_EVENTO = "1.00"
TZ_BR = ZoneInfo("America/Sao_Paulo")


class NfeEventoBuildError(ValueError):
    pass


def _txt(parent: etree._Element, tag: str, value: str) -> etree._Element:
    el = etree.SubElement(parent, f"{{{NFE_NS}}}{tag}")
    el.text = value
    return el


def build_inf_evento_id(*, access_key: str, tp_evento: str = TP_EVENTO_CANCEL, n_seq: int = 1) -> str:
    """Id = ID + tpEvento(6) + chNFe(44) + nSeqEvento(2)."""
    ch = "".join(c for c in str(access_key or "") if c.isdigit())
    te = "".join(c for c in str(tp_evento or "") if c.isdigit())
    if len(ch) != 44:
        raise NfeEventoBuildError(f"chNFe deve ter 44 dígitos (got {len(ch)})")
    if len(te) != 6:
        raise NfeEventoBuildError(f"tpEvento deve ter 6 dígitos (got {len(te)})")
    seq = max(1, int(n_seq or 1))
    return f"ID{te}{ch}{str(seq).zfill(2)[:2]}"


def build_cancel_env_evento_xml(
    *,
    access_key: str,
    cnpj: str,
    protocol: str,
    justificativa: str,
    tp_amb: str = "2",
    c_orgao: str | None = None,
    n_seq: int = 1,
    id_lote: str | int = 1,
    dh_evento: datetime | None = None,
) -> bytes:
    """
    Monta envEvento/evento/infEvento de cancelamento 110111 (sem Signature).

    justificativa: 15–255 caracteres (regra SEFAZ).
    protocol: nProt da autorização original.
    """
    ch = "".join(c for c in str(access_key or "") if c.isdigit())
    cnpj_d = "".join(c for c in str(cnpj or "") if c.isdigit())
    n_prot = "".join(c for c in str(protocol or "") if c.isdigit() or c.isalnum())
    just = (justificativa or "").strip()
    amb = str(tp_amb or "2").strip()[:1] or "2"

    if len(ch) != 44:
        raise NfeEventoBuildError("chNFe inválida")
    if len(cnpj_d) != 14:
        raise NfeEventoBuildError("CNPJ emitente inválido")
    if not n_prot:
        raise NfeEventoBuildError("nProt da autorização é obrigatório")
    if not (15 <= len(just) <= 255):
        raise NfeEventoBuildError("xJust deve ter entre 15 e 255 caracteres")

    orgao = (c_orgao or ch[:2] or UF_IBGE_CODE["SP"]).strip()
    if not orgao.isdigit():
        orgao = UF_IBGE_CODE.get(orgao.upper(), "35")

    now = dh_evento or datetime.now(TZ_BR)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_BR)
    # SEFAZ aceita offset -03:00
    dh = now.isoformat(timespec="seconds")

    inf_id = build_inf_evento_id(access_key=ch, n_seq=n_seq)
    lote = str(int(id_lote) if str(id_lote).isdigit() else 1).zfill(15)[:15]

    env = etree.Element(f"{{{NFE_NS}}}envEvento", nsmap={None: NFE_NS}, versao=VER_EVENTO)
    _txt(env, "idLote", lote)

    evento = etree.SubElement(env, f"{{{NFE_NS}}}evento", versao=VER_EVENTO)
    inf = etree.SubElement(evento, f"{{{NFE_NS}}}infEvento", Id=inf_id)
    _txt(inf, "cOrgao", orgao)
    _txt(inf, "tpAmb", amb)
    _txt(inf, "CNPJ", cnpj_d)
    _txt(inf, "chNFe", ch)
    _txt(inf, "dhEvento", dh)
    _txt(inf, "tpEvento", TP_EVENTO_CANCEL)
    _txt(inf, "nSeqEvento", str(max(1, int(n_seq or 1))))
    _txt(inf, "verEvento", VER_EVENTO)

    det = etree.SubElement(inf, f"{{{NFE_NS}}}detEvento", versao=VER_EVENTO)
    _txt(det, "descEvento", "Cancelamento")
    _txt(det, "nProt", n_prot)
    _txt(det, "xJust", just)

    return etree.tostring(env, xml_declaration=True, encoding="UTF-8")


def build_cancel_from_context(
    *,
    access_key: str,
    justificativa: str,
    context: dict[str, Any] | None = None,
) -> bytes:
    """Convenience: context com protocol, cnpj, tp_amb, uf/c_orgao."""
    ctx = context or {}
    cnpj = str(ctx.get("cnpj") or "")
    if not cnpj and len("".join(c for c in access_key if c.isdigit())) == 44:
        # chNFe: cUF(2)+AAMM(4)+CNPJ(14)+…
        digits = "".join(c for c in access_key if c.isdigit())
        cnpj = digits[6:20]
    return build_cancel_env_evento_xml(
        access_key=access_key,
        cnpj=cnpj,
        protocol=str(ctx.get("protocol") or ""),
        justificativa=justificativa,
        tp_amb=str(ctx.get("tp_amb") or "2"),
        c_orgao=str(ctx.get("c_orgao") or "") or None,
        n_seq=int(ctx.get("n_seq_evento") or 1),
        id_lote=ctx.get("id_lote") or 1,
    )
