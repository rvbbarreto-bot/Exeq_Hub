"""Contrato estrutural mínimo da DPS (SEC-P2-03 parcial — sem XSD oficial embutido).

Valida elementos obrigatórios no XML gerado pelo Hub antes do envio SEFIN.
XSD federal completo fica como evolução quando o pacote oficial estiver versionado no repo.
"""

from __future__ import annotations

from integrations.nfse.xml_safe import safe_fromstring


class DpsContractError(ValueError):
    pass


def _local(tag: str) -> str:
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return str(tag)


def assert_dps_structure(dps_xml: bytes | str) -> None:
    root = safe_fromstring(dps_xml)
    if _local(root.tag) != "DPS":
        raise DpsContractError("Raiz deve ser DPS")
    inf = None
    for child in root:
        if _local(child.tag) == "infDPS":
            inf = child
            break
    if inf is None:
        raise DpsContractError("infDPS ausente")
    if not (inf.get("Id") or "").startswith("DPS"):
        raise DpsContractError("infDPS/@Id deve iniciar com DPS")
    present = {_local(c.tag) for c in inf}
    required = {
        "tpAmb",
        "dhEmi",
        "verAplic",
        "serie",
        "nDPS",
        "dCompet",
        "cLocEmi",
        "prest",
        "toma",
        "serv",
        "valores",
    }
    missing = sorted(required - present)
    if missing:
        raise DpsContractError(f"infDPS sem elementos: {', '.join(missing)}")
