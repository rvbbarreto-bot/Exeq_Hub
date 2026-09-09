"""Parse docZip e XMLs de distribuição DFe (NT 2014.002)."""

from __future__ import annotations

import base64
import gzip
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from lxml import etree

from integrations.nfse.xml_safe import UnsafeXmlError, safe_fromstring
from integrations.sefaz_nfe.distribuicao.port import _pad_nsu

NFE_NS = "http://www.portalfiscal.inf.br/nfe"

_SCHEMA_MAP = {
    "resNFe": "resNFe",
    "procNFe": "procNFe",
    "resEvento": "resEvento",
    "procEventoNFe": "procEventoNFe",
}


class DocumentParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedDistribuicaoDocument:
    nsu: str
    schema_type: str
    access_key: str
    issuer_cnpj: str
    issuer_name: str
    recipient_cnpj: str
    number: int | None
    series: int | None
    issue_date: date | None
    total_cents: int | None
    nfe_status: str
    xml_bytes: bytes
    xml_hash: str
    raw_metadata: dict[str, Any]


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _child_text(parent: Any, name: str) -> str:
    for ch in parent:
        if _local(ch.tag) == name and ch.text:
            return ch.text.strip()
    return ""


def _digits(value: str, *, max_len: int | None = None) -> str:
    out = "".join(c for c in str(value or "") if c.isdigit())
    if max_len is not None:
        return out[:max_len]
    return out


def _parse_xml(xml_bytes: bytes) -> etree._Element:
    try:
        root = safe_fromstring(xml_bytes)
    except (etree.XMLSyntaxError, UnsafeXmlError, ValueError) as exc:
        raise DocumentParseError("XML inválido") from exc
    if root is None:
        raise DocumentParseError("XML vazio")
    return root


def detect_schema_type(xml_bytes: bytes) -> str:
    root = _parse_xml(xml_bytes)
    tag = _local(root.tag)
    return _SCHEMA_MAP.get(tag, "other")


def decode_doc_zip(*, nsu: str, schema_hint: str, payload: str | bytes) -> bytes:
    """Decodifica docZip (base64+gzip) ou retorna bytes crus."""
    if isinstance(payload, (bytes, bytearray)):
        if payload[:2] == b"\x1f\x8b" or payload.lstrip()[:5] == b"<?xml":
            return bytes(payload)
        payload = payload.decode("utf-8", errors="replace")
    raw = base64.b64decode(payload or "")
    try:
        return gzip.decompress(raw)
    except OSError:
        return raw


def _parse_issue_date(value: str) -> date | None:
    text = (value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    return None


def _money_to_cents(value: str) -> int | None:
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        from shared.money import reais_to_cents

        return reais_to_cents(Decimal(text))
    except Exception:
        return None


def _extract_access_key_from_proc(root: etree._Element) -> str:
    for el in root.iter():
        if _local(el.tag) == "infNFe":
            attr_id = el.get("Id") or el.get("id") or ""
            key = _digits(attr_id.replace("NFe", ""), max_len=44)
            if len(key) == 44:
                return key
            ch = _child_text(el, "chNFe")
            if len(ch) == 44:
                return ch
    return ""


def _extract_number_series_from_proc(root: etree._Element) -> tuple[int | None, int | None]:
    for el in root.iter():
        if _local(el.tag) == "ide":
            n_nf = _child_text(el, "nNF")
            serie = _child_text(el, "serie")
            number = int(n_nf) if n_nf.isdigit() else None
            series = int(serie) if serie.isdigit() else None
            return number, series
    return None, None


def parse_distribuicao_xml(*, nsu: str, xml_bytes: bytes) -> ParsedDistribuicaoDocument:
    root = _parse_xml(xml_bytes)
    schema_type = _SCHEMA_MAP.get(_local(root.tag), "other")
    access_key = ""
    issuer_cnpj = ""
    issuer_name = ""
    recipient_cnpj = ""
    number = None
    series = None
    issue_date = None
    total_cents = None
    nfe_status = ""

    if schema_type == "resNFe":
        access_key = _digits(_child_text(root, "chNFe"), max_len=44)
        issuer_cnpj = _digits(_child_text(root, "CNPJ"), max_len=14) or _digits(
            _child_text(root, "CPF"), max_len=11
        )
        issuer_name = _child_text(root, "xNome")[:120]
        issue_date = _parse_issue_date(_child_text(root, "dhEmi"))
        total_cents = _money_to_cents(_child_text(root, "vNF"))
        nfe_status = _child_text(root, "cSitNFe")
    elif schema_type == "procNFe":
        access_key = _extract_access_key_from_proc(root)
        number, series = _extract_number_series_from_proc(root)
        for el in root.iter():
            tag = _local(el.tag)
            if tag == "emit":
                issuer_cnpj = _digits(_child_text(el, "CNPJ"), max_len=14) or _digits(
                    _child_text(el, "CPF"), max_len=11
                )
                issuer_name = _child_text(el, "xNome")[:120]
            elif tag == "dest":
                recipient_cnpj = _digits(_child_text(el, "CNPJ"), max_len=14) or _digits(
                    _child_text(el, "CPF"), max_len=11
                )
            elif tag == "ide":
                issue_date = _parse_issue_date(_child_text(el, "dhEmi"))
            elif tag == "ICMSTot":
                total_cents = _money_to_cents(_child_text(el, "vNF"))
        nfe_status = "authorized"
    else:
        access_key = _digits(_child_text(root, "chNFe"), max_len=44)

    xml_hash = __import__("hashlib").sha256(xml_bytes).hexdigest()
    return ParsedDistribuicaoDocument(
        nsu=_pad_nsu(nsu),
        schema_type=schema_type,
        access_key=access_key,
        issuer_cnpj=issuer_cnpj,
        issuer_name=issuer_name,
        recipient_cnpj=recipient_cnpj,
        number=number,
        series=series,
        issue_date=issue_date,
        total_cents=total_cents,
        nfe_status=nfe_status,
        xml_bytes=xml_bytes,
        xml_hash=xml_hash,
        raw_metadata={"root": _local(root.tag)},
    )


class RetDistParseError(ValueError):
    pass


@dataclass(frozen=True)
class RetDistDocZip:
    nsu: str
    schema_type: str
    payload: str


@dataclass(frozen=True)
class RetDistParse:
    c_stat: str
    x_motivo: str
    ult_nsu: str
    max_nsu: str
    dh_resp: str
    documents: tuple[RetDistDocZip, ...]


def _find_ret_dist_root(root: etree._Element) -> etree._Element | None:
    if _local(root.tag) == "retDistDFeInt":
        return root
    for el in root.iter():
        if _local(el.tag) == "retDistDFeInt":
            return el
    return None


def parse_ret_dist_dfe_response(body: str | bytes) -> RetDistParse:
    """Extrai retDistDFeInt de resposta SOAP ou XML puro."""
    text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body or "")
    if not text.strip():
        raise RetDistParseError("Resposta vazia")
    try:
        root = safe_fromstring(text)
    except (etree.XMLSyntaxError, UnsafeXmlError, ValueError) as exc:
        raise RetDistParseError("SOAP/XML inválido") from exc
    if root is None:
        raise RetDistParseError("SOAP/XML inválido")

    ret = _find_ret_dist_root(root)
    if ret is None:
        fault = ""
        for el in root.iter():
            if _local(el.tag) in ("Text", "Reason", "faultstring") and el.text:
                fault = el.text.strip()
                break
        raise RetDistParseError(fault or "retDistDFeInt não encontrado")

    c_stat = _child_text(ret, "cStat")
    x_motivo = _child_text(ret, "xMotivo")
    ult_nsu = _pad_nsu(_child_text(ret, "ultNSU") or "0")
    max_nsu = _pad_nsu(_child_text(ret, "maxNSU") or ult_nsu)
    dh_resp = _child_text(ret, "dhResp")

    documents: list[RetDistDocZip] = []
    for el in ret.iter():
        if _local(el.tag) != "docZip" or not (el.text or "").strip():
            continue
        nsu = _pad_nsu(el.get("NSU") or el.get("nsu") or _child_text(el, "NSU") or "0")
        schema = el.get("schema") or el.get("Schema") or "resNFe"
        documents.append(
            RetDistDocZip(
                nsu=nsu,
                schema_type=schema,
                payload=el.text.strip(),
            )
        )

    return RetDistParse(
        c_stat=c_stat,
        x_motivo=x_motivo,
        ult_nsu=ult_nsu,
        max_nsu=max_nsu,
        dh_resp=dh_resp,
        documents=tuple(documents),
    )
