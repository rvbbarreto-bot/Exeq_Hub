"""Carta de Correção Eletrônica (CCe) — evento 110110 (U5-CCE).

Monta envEvento; assinatura + POST em HttpNfeProvider.carta_correcao.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from lxml import etree

from integrations.sefaz_nfe.access_key import UF_IBGE_CODE
from integrations.sefaz_nfe.evento_cancel import build_inf_evento_id

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
TP_EVENTO_CCE = "110110"
VER_EVENTO = "1.00"
TZ_BR = ZoneInfo("America/Sao_Paulo")
# cStat event registered (mesmos códigos do cancel em muitos retornos).
EVENTO_CCE_OK = frozenset({"135", "136"})


class NfeCceBuildError(ValueError):
    pass


def _txt(parent: etree._Element, tag: str, value: str) -> etree._Element:
    el = etree.SubElement(parent, f"{{{NFE_NS}}}{tag}")
    el.text = value
    return el


def build_cce_env_evento_xml(
    *,
    access_key: str,
    cnpj: str,
    x_correcao: str,
    tp_amb: str = "2",
    c_orgao: str | None = None,
    n_seq: int = 1,
    id_lote: str | int = 1,
    dh_evento: datetime | None = None,
) -> bytes:
    """
    Monta envEvento/evento/infEvento de CCe 110110 (sem Signature).

    x_correcao: 15–1000 caracteres (regra SEFAZ típica).
    """
    ch = "".join(c for c in str(access_key or "") if c.isdigit())
    cnpj_d = "".join(c for c in str(cnpj or "") if c.isdigit())
    corr = (x_correcao or "").strip()
    amb = str(tp_amb or "2").strip()[:1] or "2"

    if len(ch) != 44:
        raise NfeCceBuildError("chNFe inválida")
    if len(cnpj_d) != 14:
        raise NfeCceBuildError("CNPJ emitente inválido")
    if not (15 <= len(corr) <= 1000):
        raise NfeCceBuildError("xCorrecao deve ter entre 15 e 1000 caracteres")
    seq = max(1, int(n_seq or 1))
    if seq > 20:
        raise NfeCceBuildError("nSeqEvento CCe máximo 20")

    orgao = (c_orgao or ch[:2] or UF_IBGE_CODE["SP"]).strip()
    if not orgao.isdigit():
        orgao = UF_IBGE_CODE.get(orgao.upper(), "35")

    now = dh_evento or datetime.now(TZ_BR)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_BR)
    dh = now.isoformat(timespec="seconds")

    inf_id = build_inf_evento_id(access_key=ch, tp_evento=TP_EVENTO_CCE, n_seq=seq)
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
    _txt(inf, "tpEvento", TP_EVENTO_CCE)
    _txt(inf, "nSeqEvento", str(seq))
    _txt(inf, "verEvento", VER_EVENTO)

    det = etree.SubElement(inf, f"{{{NFE_NS}}}detEvento", versao=VER_EVENTO)
    _txt(det, "descEvento", "Carta de Correcao")
    _txt(det, "xCorrecao", corr)
    _txt(
        det,
        "xCondUso",
        (
            "A Carta de Correcao e disciplinada pelo paragrafo 1o-A do art. 7o "
            "do Convenio S/N, de 15 de dezembro de 1970 e pode ser utilizada "
            "para regularizacao de erro ocorrido na emissao de documento "
            "fiscal, desde que o erro nao esteja relacionado com: I - as "
            "variaveis que determinam o valor do imposto tais como: base de "
            "calculo, aliquota, diferenca de preco, quantidade, valor da "
            "operacao ou da prestacao; II - a correcao de dados cadastrais "
            "que implique mudanca do remetente ou do destinatario; III - a "
            "data de emissao ou de saida."
        ),
    )

    return etree.tostring(env, xml_declaration=True, encoding="UTF-8")


def build_cce_from_context(
    *,
    access_key: str,
    x_correcao: str,
    context: dict[str, Any] | None = None,
) -> bytes:
    ctx = context or {}
    cnpj = str(ctx.get("cnpj") or "")
    if not cnpj and len("".join(c for c in access_key if c.isdigit())) == 44:
        digits = "".join(c for c in access_key if c.isdigit())
        cnpj = digits[6:20]
    return build_cce_env_evento_xml(
        access_key=access_key,
        cnpj=cnpj,
        x_correcao=x_correcao,
        tp_amb=str(ctx.get("tp_amb") or "2"),
        c_orgao=str(ctx.get("c_orgao") or "") or None,
        n_seq=int(ctx.get("n_seq_evento") or 1),
        id_lote=ctx.get("id_lote") or 1,
    )
