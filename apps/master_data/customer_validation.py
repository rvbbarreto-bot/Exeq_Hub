"""Validação de endereço fiscal do tomador (NF-e modelo 55)."""

from __future__ import annotations


def normalize_customer_address(address: dict | None) -> dict:
    addr = dict(address or {})
    ibge = "".join(
        ch
        for ch in str(
            addr.get("codigo_municipio_ibge") or addr.get("codigo_ibge") or ""
        )
        if ch.isdigit()
    )[:7]
    if ibge:
        addr["codigo_municipio_ibge"] = ibge
        addr["codigo_ibge"] = ibge
    uf = str(addr.get("uf") or addr.get("UF") or "").upper().strip()[:2]
    if uf:
        addr["uf"] = uf
    return addr


def validate_customer_fiscal_address(address: dict | None) -> None:
    """Campos exigidos pelo motor fiscal NF-e (build_validation)."""
    addr = normalize_customer_address(address)
    logradouro = (addr.get("logradouro") or addr.get("street") or "").strip()
    uf = (addr.get("uf") or "").strip()
    ibge = (addr.get("codigo_municipio_ibge") or addr.get("codigo_ibge") or "").strip()

    if not logradouro:
        raise ValueError("Informe o logradouro do tomador.")
    if len(uf) != 2:
        raise ValueError("Informe a UF do tomador (2 letras).")
    if len(ibge) != 7:
        raise ValueError("Informe o código IBGE do município (7 dígitos).")
