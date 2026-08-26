"""Validações de catálogo de serviços (CTN / operação)."""

from __future__ import annotations


def normalize_ctn_iss(value: str) -> str:
    """Normaliza CTN (cTribNac) para 6 dígitos ou vazio."""
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) != 6:
        raise ValueError(
            "Código tributação nacional ISS deve ter exatamente 6 dígitos (Anexo B NFS-e)."
        )
    return digits


def assert_service_emittable_nfse(*, operation_kind: str) -> None:
    from apps.master_data.models import ServiceCatalogItem

    if operation_kind == ServiceCatalogItem.OperationKind.LOCACAO_BEM:
        raise ValueError(
            "Locação de bem não gera NFS-e/ISS. Use faturamento próprio (sem emissão fiscal)."
        )
