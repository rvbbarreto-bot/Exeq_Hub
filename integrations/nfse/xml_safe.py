"""Parse XML endurecido (SEC-P1-03 / XXE).

lxml com entidades externas e rede desligadas. DTD/ENTITY bloqueados
(XML oficial NFS-e não usa DTD). Usar em todo caminho DPS/evento/DANFSe.
"""

from __future__ import annotations

from lxml import etree

_SAFE_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False,
)


class UnsafeXmlError(etree.XMLSyntaxError):
    """XML com DTD/ENTITY — rejeitado fail-closed."""


def safe_fromstring(raw: bytes | str) -> etree._Element:
    data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    probe = data[:4096].upper()
    if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
        raise UnsafeXmlError("DTD/ENTITY não permitido no XML NFS-e", "", 0, 0, "")
    return etree.fromstring(data, parser=_SAFE_PARSER)
