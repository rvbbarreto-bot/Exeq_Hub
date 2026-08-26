"""Sprint D — hints de compliance cadastral (soft, não bloqueia emissão)."""

from __future__ import annotations

from apps.master_data.models import Provider, ServiceCatalogItem

# CNAE(s) Receita típicos por operação comercial (EXEQ Lab — validar com contador).
SERVICE_CNAE_HINTS: dict[str, tuple[str, ...]] = {
    "SVC-SUP-TI": ("6209100",),
    "SVC-DEV-ENC": ("6201501",),
    "SVC-SW-CUST": ("6202300",),
    "SVC-SW-PAD": ("6203100",),
    "SVC-CONS-TI": ("6204000",),
    "SVC-HOST-SaaS": ("6311900",),
    "SVC-CORRET-IM": ("6821801",),
    "SVC-ADM-IM": ("6822600",),
    "OP-LOC-AUTO": ("7711000",),
    "OP-LOC-OUT": ("7719599",),
}


def normalize_cnae_digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())[:7]


def provider_cnae_digits(provider: Provider) -> set[str]:
    out: set[str] = set()
    principal = normalize_cnae_digits(getattr(provider, "cnae_principal", "") or "")
    if principal:
        out.add(principal)
    secundarios = getattr(provider, "cnaes_secundarios", None) or []
    if isinstance(secundarios, list):
        for raw in secundarios:
            digits = normalize_cnae_digits(str(raw))
            if digits:
                out.add(digits)
    addr = provider.address if isinstance(provider.address, dict) else {}
    legacy = addr.get("cnaes_secundarios") or []
    if isinstance(legacy, list):
        for raw in legacy:
            digits = normalize_cnae_digits(str(raw))
            if digits:
                out.add(digits)
    return out


def _cnae_matches(provider_digits: set[str], hint: str) -> bool:
    hint_digits = normalize_cnae_digits(hint)
    if not hint_digits:
        return True
    if hint_digits in provider_digits:
        return True
    # Divisão CNAE (4 dígitos) — tolerância operacional.
    prefix = hint_digits[:4]
    return any(d[:4] == prefix for d in provider_digits)


def service_cnae_compliance_warnings(
    *,
    provider: Provider,
    service: ServiceCatalogItem,
) -> list[str]:
    """
    Retorna avisos soft quando o CNAE do CNPJ não cobre o hint da operação.
    Não bloqueia emissão — orientação ao operador/contador.
    """
    if service.operation_kind == ServiceCatalogItem.OperationKind.LOCACAO_BEM:
        return []
    hints = SERVICE_CNAE_HINTS.get((service.service_code or "").strip())
    if not hints:
        return []
    provider_digits = provider_cnae_digits(provider)
    if not provider_digits:
        return [
            f"CNAE do prestador não cadastrado — valide enquadramento do serviço "
            f"{service.service_code} ({service.description[:60]})."
        ]
    if any(_cnae_matches(provider_digits, h) for h in hints):
        return []
    expected = ", ".join(hints)
    found = ", ".join(sorted(provider_digits))
    return [
        f"CNAE(s) do CNPJ ({found}) não incluem hint típico ({expected}) para "
        f"{service.service_code}. Confirme enquadramento LC 116 / item municipal."
    ]
