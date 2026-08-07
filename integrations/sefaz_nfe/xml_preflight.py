"""RF-41 / EX-PRE-04 — preflight estrutural do XML NFe antes do POST SEFAZ.

Não embute XSD oficial. Valida árvore mínima + Signature + ICMSTot + det≥1.
Opcional: se `NFE_XSD_PATH` apontar para XSD local e lxml.etree.XMLSchema existir —
validação extra best-effort (não bloqueia se path ausente).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from integrations.nfse.xml_safe import safe_fromstring


class NfeXmlPreflightError(ValueError):
    """XML inválido / incompleto para envio (pre-tx)."""


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    errors: tuple[str, ...]

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise NfeXmlPreflightError("; ".join(self.errors))


def preflight_signed_nfe(xml: bytes | str, *, require_signature: bool = True) -> PreflightResult:
    """Exige NFe bem-formada com ide/emit/dest/det/total e Signature (pós-sign)."""
    errors: list[str] = []
    try:
        root = safe_fromstring(xml)
    except Exception as exc:  # noqa: BLE001
        return PreflightResult(ok=False, errors=(f"xml_malformed:{exc}",))

    if _local(root.tag) != "NFe":
        errors.append(f"root_expected_NFe_got_{_local(root.tag)}")

    by_local: dict[str, list] = {}
    for el in root.iter():
        by_local.setdefault(_local(el.tag), []).append(el)

    for name in ("infNFe", "ide", "emit", "dest", "total", "det"):
        if name not in by_local:
            errors.append(f"missing_{name}")

    dets = by_local.get("det") or []
    if not dets:
        errors.append("missing_det")
    elif len(dets) < 1:
        errors.append("det_empty")

    if "ICMSTot" not in by_local and "total" in by_local:
        # total sem ICMSTot é rejeição comum
        errors.append("missing_ICMSTot")

    ide = (by_local.get("ide") or [None])[0]
    if ide is not None:
        fields = {_local(c.tag): (c.text or "").strip() for c in ide}
        if fields.get("mod") and fields["mod"] != "55":
            errors.append(f"mod_not_55:{fields['mod']}")
        if fields.get("tpAmb") and fields["tpAmb"] not in ("1", "2"):
            errors.append(f"tpAmb_invalid:{fields['tpAmb']}")
        if fields.get("serie") is not None and fields.get("serie") == "":
            errors.append("serie_empty")

    emit = (by_local.get("emit") or [None])[0]
    if emit is not None:
        emit_fields = {_local(c.tag): (c.text or "").strip() for c in emit}
        cnpj = "".join(ch for ch in (emit_fields.get("CNPJ") or "") if ch.isdigit())
        if cnpj and len(cnpj) != 14:
            errors.append(f"emit_cnpj_len:{len(cnpj)}")

    inf = (by_local.get("infNFe") or [None])[0]
    if inf is not None:
        inf_id = inf.get("Id") or ""
        if inf_id and not inf_id.startswith("NFe"):
            errors.append("infNFe_Id_prefix")
        if inf_id.startswith("NFe"):
            digits = "".join(ch for ch in inf_id[3:] if ch.isdigit())
            if len(digits) != 44:
                errors.append("infNFe_Id_key_len")

    if require_signature and "Signature" not in by_local:
        errors.append("missing_Signature")

    # XSD opcional (ops anexa pacotes)
    xsd_path = ""
    try:
        from django.conf import settings as dj_settings

        xsd_path = (getattr(dj_settings, "NFE_XSD_PATH", None) or "").strip()
    except Exception:  # noqa: BLE001 — settings não configurados em unit isolado
        xsd_path = ""
    if xsd_path and Path(xsd_path).is_file():
        try:
            from lxml import etree

            schema = etree.XMLSchema(etree.parse(xsd_path))
            if not schema.validate(root):
                errors.append("xsd_schema_failed")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"xsd_load_error:{type(exc).__name__}")

    return PreflightResult(ok=not errors, errors=tuple(errors))
