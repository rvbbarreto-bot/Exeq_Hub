"""RF-41 / EX-PRE-04 — preflight estrutural do XML NFe antes do POST SEFAZ.

Não embute XSD oficial (pacote ~grande / versionado ops). Valida árvore mínima,
assíncrona de envio e coerência de chaves óbvias — falha = sem HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

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

    ide = (by_local.get("ide") or [None])[0]
    if ide is not None:
        mods = [(_local(c.tag), (c.text or "").strip()) for c in ide]
        fields = {k: v for k, v in mods}
        if fields.get("mod") not in ("", "55", None) and fields.get("mod") != "55":
            # empty ok only if builder omitted; se presente deve ser 55
            if fields.get("mod") and fields["mod"] != "55":
                errors.append(f"mod_not_55:{fields['mod']}")
        if fields.get("tpAmb") and fields["tpAmb"] not in ("1", "2"):
            errors.append(f"tpAmb_invalid:{fields['tpAmb']}")

    inf = (by_local.get("infNFe") or [None])[0]
    if inf is not None:
        inf_id = inf.get("Id") or ""
        if inf_id and not inf_id.startswith("NFe"):
            errors.append("infNFe_Id_prefix")
        if inf_id and len(inf_id) == 47:  # NFe + 44
            digits = "".join(ch for ch in inf_id[3:] if ch.isdigit())
            if len(digits) != 44:
                errors.append("infNFe_Id_key_len")

    if require_signature and "Signature" not in by_local:
        errors.append("missing_Signature")

    return PreflightResult(ok=not errors, errors=tuple(errors))
