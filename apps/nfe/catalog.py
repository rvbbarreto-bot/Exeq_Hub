"""RF-100 lite — catálogo NCM/CFOP MVP lab (versionado em código)."""

from __future__ import annotations

from typing import Any

# Bump quando alterar allowlists (gravado no snapshot)
CATALOG_VERSION = "nfe-mvp-1.0"

# Lab + volume comum SN varejo/serviços complementares mercadoria
ALLOWED_NCM = frozenset(
    {
        "21069090",
        "22021000",
        "22030000",
        "30049099",
        "33049910",
        "34011190",
        "39269090",
        "40169990",
        "48201000",
        "49019900",
        "61091000",
        "62034200",
        "63026000",
        "64029990",
        "84713012",
        "84713019",
        "85171231",
        "85285220",
        "87089990",
        "94036000",
    }
)

ALLOWED_CFOP = frozenset(
    {
        "5101",
        "5102",
        "5405",
        "5405",  # dup harmless
        "5910",
        "6101",
        "6102",
        "6405",
        "6910",
    }
)


def catalog_meta() -> dict[str, Any]:
    return {
        "catalog_version": CATALOG_VERSION,
        "ncm_count": len(ALLOWED_NCM),
        "cfop_count": len(ALLOWED_CFOP),
    }


def validate_ncm(ncm: str) -> str | None:
    code = "".join(ch for ch in str(ncm or "") if ch.isdigit())
    if len(code) != 8:
        return "NCM deve ter 8 dígitos"
    if code not in ALLOWED_NCM:
        return f"NCM {code} fora do catálogo MVP ({CATALOG_VERSION}); amplie allowlist lab"
    return None


def validate_cfop_catalog(cfop: str) -> str | None:
    code = "".join(ch for ch in str(cfop or "") if ch.isdigit())
    if len(code) != 4:
        return "CFOP inválido"
    if code not in ALLOWED_CFOP:
        return f"CFOP {code} fora do catálogo MVP ({CATALOG_VERSION})"
    return None
