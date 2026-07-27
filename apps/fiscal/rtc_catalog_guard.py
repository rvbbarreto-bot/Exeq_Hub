"""Pilar 5 — enforcement do catálogo nacional de serviços na emissão."""

from __future__ import annotations

from django.conf import settings

from apps.fiscal.exceptions import NationalCatalogError
from apps.master_data.national_service_import import get_published_national_services


def assert_national_service_code(*, service) -> dict:
    """
    Se há lista nacional publicada e RTC_ENFORCE_NATIONAL_CATALOG=true,
    exige codigo_tributacao_nacional_iss presente na lista.
    """
    if not getattr(settings, "RTC_ENFORCE_NATIONAL_CATALOG", True):
        return {"status": "skipped", "reason": "enforce_disabled"}

    version, items = get_published_national_services()
    if version is None:
        return {"status": "skipped", "reason": "no_published_national_list"}

    code = (getattr(service, "codigo_tributacao_nacional_iss", None) or "").strip()
    if not code:
        raise NationalCatalogError(
            "Serviço sem código de tributação nacional. "
            "Materialize a Lista Nacional no tenant ou informe o código oficial."
        )

    exists = items.filter(codigo=code).exists()
    if not exists:
        # tolerância: código com zeros à esquerda removidos na importação
        digits = "".join(ch for ch in code if ch.isdigit())
        exists = bool(digits) and items.filter(codigo=digits).exists()
        if exists:
            code = digits

    if not exists:
        raise NationalCatalogError(
            f"Código nacional '{code}' não consta da lista publicada "
            f"({version.version_label}). Atualize o catálogo do serviço."
        )

    return {
        "status": "ok",
        "version": version.version_label,
        "codigo": code,
        "row_count": version.row_count,
    }
