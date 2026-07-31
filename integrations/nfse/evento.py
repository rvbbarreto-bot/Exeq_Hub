"""Pedido de Registro de Evento (cancelamento e101101) — RF-31."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from lxml import etree

NFSE_NS = "http://www.sped.fazenda.gov.br/nfse"
EVENTO_VERSAO = "1.01"
VER_APLIC = "EXEQHUB_1.0"
TZ_BR = ZoneInfo("America/Sao_Paulo")
CODIGO_CANCELAMENTO = "e101101"
CODIGO_EVENTO_DIGITS = "101101"


class EventoBuildError(ValueError):
    pass


def build_ped_reg_id(*, chave_acesso: str, codigo_evento: str = CODIGO_EVENTO_DIGITS) -> str:
    """Id = PRE + chave(50) + tipoEvento(6) — TSIdPedRegEvt = PRE[0-9]{56}."""
    chave = "".join(ch for ch in chave_acesso if ch.isdigit())
    codigo = "".join(ch for ch in codigo_evento if ch.isdigit())
    if len(chave) != 50:
        raise EventoBuildError(f"chaveAcesso deve ter 50 dígitos (got {len(chave)})")
    if len(codigo) != 6:
        raise EventoBuildError(f"codigo evento deve ter 6 dígitos (got {len(codigo)})")
    return f"PRE{chave}{codigo}"


def build_cancel_ped_reg_evento_xml(
    *,
    chave_acesso: str,
    autor_cnpj: str,
    x_motivo: str,
    c_motivo: int | str = 1,
    tp_amb: int = 1,
    n_ped: int = 1,
    dh_evento: datetime | None = None,
    ver_aplic: str = VER_APLIC,
) -> bytes:
    """Monta pedRegEvento/infPedReg/e101101 (ainda sem Signature)."""
    _ = n_ped  # removido do leiaute/Id (jan/2026)
    chave = "".join(ch for ch in chave_acesso if ch.isdigit())
    cnpj = "".join(ch for ch in autor_cnpj if ch.isdigit())
    motivo = (x_motivo or "").strip()
    if len(chave) != 50:
        raise EventoBuildError("chaveAcesso inválida")
    if len(cnpj) != 14:
        raise EventoBuildError("CNPJAutor inválido")
    if not (15 <= len(motivo) <= 255):
        raise EventoBuildError("xMotivo deve ter entre 15 e 255 caracteres")

    now = dh_evento or datetime.now(TZ_BR)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_BR)

    ped_id = build_ped_reg_id(chave_acesso=chave, codigo_evento=CODIGO_EVENTO_DIGITS)
    root = etree.Element(f"{{{NFSE_NS}}}pedRegEvento", nsmap={None: NFSE_NS})
    root.set("versao", EVENTO_VERSAO)
    inf = etree.SubElement(root, f"{{{NFSE_NS}}}infPedReg")
    inf.set("Id", ped_id)
    _txt(inf, "tpAmb", str(int(tp_amb)))
    _txt(inf, "verAplic", ver_aplic)
    _txt(inf, "dhEvento", now.isoformat(timespec="seconds"))
    _txt(inf, "CNPJAutor", cnpj)
    _txt(inf, "chNFSe", chave)

    evt = etree.SubElement(inf, f"{{{NFSE_NS}}}{CODIGO_CANCELAMENTO}")
    _txt(evt, "xDesc", "Cancelamento de NFS-e")
    _txt(evt, "cMotivo", str(int(c_motivo)))
    _txt(evt, "xMotivo", motivo)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def build_cancel_evento_from_issue(
    issue,
    *,
    justificativa: str,
    codigo_cancelamento: int | None = None,
    tp_amb: int = 1,
) -> bytes:
    """Convenience a partir de NfIssue autorizada."""
    chave = (issue.focus_ref or "").strip()
    cnpj = "".join(ch for ch in (getattr(issue.provider, "document", "") or "") if ch.isdigit())
    return build_cancel_ped_reg_evento_xml(
        chave_acesso=chave,
        autor_cnpj=cnpj,
        x_motivo=justificativa,
        c_motivo=codigo_cancelamento or 1,
        tp_amb=tp_amb,
    )


def _txt(parent: etree._Element, tag: str, value: str) -> None:
    el = etree.SubElement(parent, f"{{{NFSE_NS}}}{tag}")
    el.text = value
