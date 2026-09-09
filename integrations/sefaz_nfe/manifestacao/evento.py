"""Eventos de manifestação do destinatário (2102xx) — NT MOC NF-e."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from lxml import etree

from integrations.sefaz_nfe.access_key import UF_IBGE_CODE
from integrations.sefaz_nfe.evento_cancel import NfeEventoBuildError, build_inf_evento_id

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
VER_EVENTO = "1.00"
TZ_BR = ZoneInfo("America/Sao_Paulo")

TP_EVENTO_CIENCIA = "210210"
TP_EVENTO_CONFIRMACAO = "210200"
TP_EVENTO_DESCONHECIMENTO = "210220"
TP_EVENTO_NAO_REALIZADA = "210240"

_MANIFEST_SPECS: dict[str, dict[str, Any]] = {
    TP_EVENTO_CIENCIA: {"desc": "Ciencia da Emissao", "needs_just": False},
    TP_EVENTO_CONFIRMACAO: {"desc": "Confirmacao da Operacao", "needs_just": False},
    TP_EVENTO_DESCONHECIMENTO: {"desc": "Desconhecimento da Operacao", "needs_just": False},
    TP_EVENTO_NAO_REALIZADA: {"desc": "Operacao nao Realizada", "needs_just": True},
}


def _txt(parent: etree._Element, tag: str, value: str) -> etree._Element:
    el = etree.SubElement(parent, f"{{{NFE_NS}}}{tag}")
    el.text = value
    return el


def _c_orgao_from_key(access_key: str) -> str:
    ch = "".join(c for c in access_key if c.isdigit())[:44]
    if len(ch) >= 2 and ch[:2].isdigit():
        return ch[:2]
    return UF_IBGE_CODE["SP"]


def build_manifest_env_evento_xml(
    *,
    access_key: str,
    cnpj: str,
    tp_evento: str,
    tp_amb: str = "2",
    n_seq: int = 1,
    id_lote: str | int = 1,
    dh_evento: datetime | None = None,
    justificativa: str | None = None,
) -> bytes:
    """Monta envEvento de manifestação do destinatário (sem assinatura)."""
    spec = _MANIFEST_SPECS.get(str(tp_evento or "").strip())
    if spec is None:
        raise NfeEventoBuildError(f"tpEvento manifestação inválido: {tp_evento}")

    ch = "".join(c for c in str(access_key or "") if c.isdigit())
    cnpj_d = "".join(c for c in str(cnpj or "") if c.isdigit())
    amb = str(tp_amb or "2").strip()[:1] or "2"
    just = (justificativa or "").strip()

    if len(ch) != 44:
        raise NfeEventoBuildError("chNFe inválida")
    if len(cnpj_d) != 14:
        raise NfeEventoBuildError("CNPJ destinatário inválido")
    if spec["needs_just"] and not (15 <= len(just) <= 255):
        raise NfeEventoBuildError("xJust deve ter entre 15 e 255 caracteres")

    orgao = _c_orgao_from_key(ch)
    now = dh_evento or datetime.now(TZ_BR)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_BR)
    dh = now.isoformat(timespec="seconds")
    te = str(tp_evento).strip()
    seq = max(1, int(n_seq or 1))
    inf_id = build_inf_evento_id(access_key=ch, tp_evento=te, n_seq=seq)
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
    _txt(inf, "tpEvento", te)
    _txt(inf, "nSeqEvento", str(seq))
    _txt(inf, "verEvento", VER_EVENTO)

    det = etree.SubElement(inf, f"{{{NFE_NS}}}detEvento", versao=VER_EVENTO)
    _txt(det, "descEvento", str(spec["desc"]))
    if spec["needs_just"]:
        _txt(det, "xJust", just)

    return etree.tostring(env, xml_declaration=True, encoding="UTF-8")
