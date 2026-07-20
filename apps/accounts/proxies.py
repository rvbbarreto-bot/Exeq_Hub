from datetime import date

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.accounts.exceptions import ElectronicProxyNotUsableError
from apps.accounts.models import ElectronicProxy


USABLE_PROXY_STATUSES = frozenset(
    {
        ElectronicProxy.Status.ACTIVE,
        ElectronicProxy.Status.EXPIRING,
    }
)


def refresh_proxy_status(proxy: ElectronicProxy) -> ElectronicProxy:
    if proxy.status == ElectronicProxy.Status.REVOKED:
        return proxy
    today = timezone.localdate()
    new_status = proxy.status
    if proxy.valid_to and proxy.valid_to < today:
        new_status = ElectronicProxy.Status.EXPIRED
    elif proxy.valid_to and (proxy.valid_to - today).days <= 30:
        if proxy.status in {
            ElectronicProxy.Status.ACTIVE,
            ElectronicProxy.Status.EXPIRING,
            ElectronicProxy.Status.PENDING,
        }:
            new_status = ElectronicProxy.Status.EXPIRING
    elif proxy.status == ElectronicProxy.Status.PENDING and proxy.valid_from <= today:
        new_status = ElectronicProxy.Status.ACTIVE
    if new_status != proxy.status:
        proxy.status = new_status
        proxy.save(update_fields=["status", "updated_at"])
    return proxy


def get_usable_proxy(
    *,
    tenant,
    principal_cnpj: str,
    service_code: str = "PGDASD",
    on_date: date | None = None,
) -> ElectronicProxy | None:
    digits = "".join(ch for ch in principal_cnpj if ch.isdigit())
    day = on_date or timezone.localdate()
    qs = (
        ElectronicProxy.objects.filter(
            tenant=tenant,
            principal_cnpj=digits,
            status__in=list(USABLE_PROXY_STATUSES),
            valid_from__lte=day,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=day))
        .order_by("-valid_from")
    )
    for proxy in qs:
        refresh_proxy_status(proxy)
        proxy.refresh_from_db()
        if proxy.status not in USABLE_PROXY_STATUSES:
            continue
        codes = proxy.ecac_service_codes or []
        if codes and service_code not in codes and "PGDASD" not in codes:
            continue
        return proxy
    return None


def assert_electronic_proxy_usable(
    *,
    tenant,
    principal_cnpj: str,
    service_code: str = "PGDASD",
) -> ElectronicProxy:
    proxy = get_usable_proxy(
        tenant=tenant,
        principal_cnpj=principal_cnpj,
        service_code=service_code,
    )
    if proxy is None:
        raise ElectronicProxyNotUsableError(
            "Procuração eletrônica e-CAC ausente ou inválida para o CNPJ/serviço DAS"
        )
    return proxy


def das_requires_electronic_proxy() -> bool:
    if getattr(settings, "DAS_REQUIRE_ELECTRONIC_PROXY", False):
        return True
    mode = (getattr(settings, "RECEITA_HTTP_MODE", None) or "stub").lower()
    return mode == "http"
