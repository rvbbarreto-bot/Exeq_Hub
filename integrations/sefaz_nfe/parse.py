"""Parse de respostas SEFAZ NF-e 4.00 — autorizacao / ret / consulta (I4–I5).

Preferência por infProt; não confunde cStat de lote (ex.: 104) com protocolo (ex.: 100).
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

# Mapas fiscais usuais retEnviNFe / retConsReciNFe / retConsSitNFe / infProt (Manual MOC).
_AUTHORIZED = frozenset({"100", "150"})
_POLLING = frozenset({"103", "105"})
_DENEGADA = frozenset({"110", "301", "302"})
_LOTE_ROOTS = frozenset(
    {
        "retEnviNFe",
        "retConsReciNFe",
        "retConsSitNFe",
    }
)


@dataclass(frozen=True)
class AutorizacaoParse:
    c_stat: str = ""
    x_motivo: str = ""
    protocol: str = ""
    access_key: str = ""
    lote_c_stat: str = ""
    lote_x_motivo: str = ""
    n_rec: str = ""  # recibo do lote (I5)


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _child_text(parent: ET.Element, name: str) -> str:
    for ch in parent:
        if _local(ch.tag) == name and ch.text:
            return ch.text.strip()
    return ""


def parse_autorizacao_response(body: str | bytes) -> AutorizacaoParse:
    """
    Extrai cStat / xMotivo / nProt / chNFe / nRec da resposta SOAP ou XML puro.

    Prioridade: `infProt` com cStat fiscal; senão raiz de retorno de lote/consulta.
    """
    if body is None:
        return AutorizacaoParse()
    text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
    if not text.strip():
        return AutorizacaoParse()

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return AutorizacaoParse()

    lote_stat = ""
    lote_mot = ""
    n_rec = ""
    for el in root.iter():
        tag = _local(el.tag)
        if tag in _LOTE_ROOTS:
            lote_stat = _child_text(el, "cStat") or lote_stat
            lote_mot = _child_text(el, "xMotivo") or lote_mot
        if tag == "infRec":
            n_rec = _child_text(el, "nRec") or n_rec
        if tag == "nRec" and el.text and not n_rec:
            n_rec = el.text.strip()

    prots: list[AutorizacaoParse] = []
    for el in root.iter():
        if _local(el.tag) != "infProt":
            continue
        prots.append(
            AutorizacaoParse(
                c_stat=_child_text(el, "cStat"),
                x_motivo=_child_text(el, "xMotivo"),
                protocol=_child_text(el, "nProt"),
                access_key=_child_text(el, "chNFe"),
                lote_c_stat=lote_stat,
                lote_x_motivo=lote_mot,
                n_rec=n_rec,
            )
        )

    if prots:
        scored = sorted(
            prots,
            key=lambda p: (
                1 if p.access_key else 0,
                1
                if p.c_stat in _AUTHORIZED
                or p.c_stat in _DENEGADA
                or (p.c_stat and p.c_stat not in _POLLING and p.c_stat != "104")
                else 0,
                1 if p.protocol else 0,
            ),
            reverse=True,
        )
        best = scored[0]
        return AutorizacaoParse(
            c_stat=best.c_stat or lote_stat,
            x_motivo=best.x_motivo or lote_mot,
            protocol=best.protocol,
            access_key=best.access_key,
            lote_c_stat=lote_stat,
            lote_x_motivo=lote_mot,
            n_rec=n_rec,
        )

    if lote_stat:
        return AutorizacaoParse(
            c_stat=lote_stat,
            x_motivo=lote_mot,
            lote_c_stat=lote_stat,
            lote_x_motivo=lote_mot,
            n_rec=n_rec,
        )

    first_stat = ""
    first_mot = ""
    first_prot = ""
    first_ch = ""
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "cStat" and el.text and not first_stat:
            first_stat = el.text.strip()
        elif tag == "xMotivo" and el.text and not first_mot:
            first_mot = el.text.strip()
        elif tag == "nProt" and el.text and not first_prot:
            first_prot = el.text.strip()
        elif tag == "chNFe" and el.text and not first_ch:
            first_ch = el.text.strip()
    return AutorizacaoParse(
        c_stat=first_stat,
        x_motivo=first_mot,
        protocol=first_prot,
        access_key=first_ch,
        n_rec=n_rec,
    )


# Evento cancelamento registrado e vinculado (MOC).
_EVENTO_CANCEL_OK = frozenset({"135", "155"})


def map_cstat_to_status(c_stat: str) -> str:
    """authorized | rejected | polling | failed | cancelled (evento)."""
    code = (c_stat or "").strip()
    if code in _AUTHORIZED:
        return "authorized"
    if code in _EVENTO_CANCEL_OK:
        return "cancelled"
    if code in _POLLING or code == "104":
        # 104 sem infProt útil → polling (I5 completa consulta do recibo)
        return "polling"
    if code in _DENEGADA:
        return "rejected"
    if code and code.isdigit() and len(code) <= 3:
        return "rejected"
    if code:
        return "failed"
    return "failed"


def parse_evento_response(body: str | bytes) -> AutorizacaoParse:
    """
    Extrai cStat/xMotivo/nProt/chNFe de retEnvEvento / retEvento / infEvento.

    Preferência: infEvento do retorno (não cStat do lote 128).
    """
    if body is None:
        return AutorizacaoParse()
    text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
    if not text.strip():
        return AutorizacaoParse()
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return AutorizacaoParse()

    lote_stat = ""
    lote_mot = ""
    for el in root.iter():
        if _local(el.tag) == "retEnvEvento":
            lote_stat = _child_text(el, "cStat") or lote_stat
            lote_mot = _child_text(el, "xMotivo") or lote_mot

    # retEvento/infEvento — desfecho do evento
    for el in root.iter():
        if _local(el.tag) != "infEvento":
            continue
        # ignora infEvento de envio (tem tpEvento mas costuma vir no request; no response tem cStat)
        c_stat = _child_text(el, "cStat")
        if not c_stat:
            continue
        return AutorizacaoParse(
            c_stat=c_stat,
            x_motivo=_child_text(el, "xMotivo") or lote_mot,
            protocol=_child_text(el, "nProt"),
            access_key=_child_text(el, "chNFe"),
            lote_c_stat=lote_stat,
            lote_x_motivo=lote_mot,
        )

    if lote_stat:
        return AutorizacaoParse(
            c_stat=lote_stat,
            x_motivo=lote_mot,
            lote_c_stat=lote_stat,
            lote_x_motivo=lote_mot,
        )
    # fallback genérico
    return parse_autorizacao_response(text)



def sanitize_sefaz_raw(raw: dict | None, *, max_body: int = 1500) -> dict:
    """Remove/trunca campos sensíveis ou volumosos para event.metadata."""
    if not raw:
        return {}
    out: dict = {}
    for k, v in raw.items():
        if k in {"password", "pfx", "pfx_bytes", "cert", "key", "signed_xml", "xml_nfe", "xml"}:
            continue
        if k == "body" and isinstance(v, str):
            out[k] = v[:max_body] + ("…" if len(v) > max_body else "")
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = sanitize_sefaz_raw(v, max_body=max_body)
        else:
            out[k] = str(v)[:200]
    return out
