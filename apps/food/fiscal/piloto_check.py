"""Checklist piloto produção — iFood × NFC-e."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from apps.accounts.models import Tenant
from apps.accounts.tenant_emission import nfce_tenant_opt_in
from apps.food.fiscal.metrics import compute_ifood_fiscal_piloto_kpis
from apps.food.models import FoodMarketplaceConnection, FoodOrder, FoodProduct
from apps.master_data.models import Provider
from apps.nfce.services import nfce_feature_enabled


def _beat_task(name: str) -> dict[str, Any] | None:
    beat = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
    for _key, spec in beat.items():
        if spec.get("task") == name:
            return spec
    return None


def run_ifood_fiscal_piloto_checks(
    *,
    tenant: Tenant,
    strict_prod: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(cid: str, ok: bool, detail: str, *, required: bool = True) -> None:
        checks.append({"id": cid, "ok": ok, "detail": detail, "required": required})

    debug = bool(getattr(settings, "DEBUG", False))
    add(
        "PILOT-01-DEBUG",
        (not debug) if strict_prod else True,
        "DEBUG=False" if not debug else "DEBUG=True (aceitável em lab; host piloto exige False)",
        required=strict_prod,
    )

    eager = bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))
    add(
        "PILOT-02-CELERY-EAGER",
        (not eager) if strict_prod else True,
        "CELERY_TASK_ALWAYS_EAGER=false"
        if not eager
        else "CELERY_TASK_ALWAYS_EAGER=true (desligar no host piloto)",
        required=strict_prod,
    )

    nfce_on = nfce_feature_enabled()
    add(
        "PILOT-03-NFCE-GLOBAL",
        nfce_on,
        f"NFCE_ENABLED={getattr(settings, 'NFCE_ENABLED', False)}",
    )

    add(
        "PILOT-04-NFE-GLOBAL",
        bool(getattr(settings, "NFE_ENABLED", False)),
        f"NFE_ENABLED={getattr(settings, 'NFE_ENABLED', False)}",
    )

    add(
        "PILOT-05-TENANT-NFCE",
        nfce_tenant_opt_in(tenant),
        "Tenant com nfce_enabled no settings",
    )

    fe = (getattr(settings, "FIELD_ENCRYPTION_KEY", "") or "").strip()
    add(
        "PILOT-06-FIELD-ENCRYPTION",
        bool(fe) and not fe.startswith("replace-with"),
        "FIELD_ENCRYPTION_KEY configurada",
    )

    provider = Provider.objects.filter(tenant=tenant, is_active=True).order_by("created_at").first()
    uf = ""
    if provider and isinstance(provider.address, dict):
        uf = str(provider.address.get("uf") or "").upper()
    add(
        "PILOT-07-PROVIDER",
        provider is not None and uf == "SP",
        f"Emitente ativo SP: {provider.legal_name if provider else 'nenhum'} ({uf or '-'})",
    )

    csc = (getattr(settings, "NFCE_CSC_TOKEN", "") or "").strip()
    add(
        "PILOT-08-CSC",
        bool(csc),
        "NFCE_CSC_TOKEN definido" if csc else "NFCE_CSC_TOKEN vazio (obrigatório em HTTP real)",
        required=False,
    )

    mp_mode = (getattr(settings, "MARKETPLACE_HTTP_MODE", "stub") or "stub").lower()
    conn = FoodMarketplaceConnection.objects.filter(
        tenant=tenant,
        provider=FoodMarketplaceConnection.Provider.IFOOD,
        is_active=True,
    ).first()
    add(
        "PILOT-09-IFOOD-CONNECTION",
        conn is not None,
        f"Conexão iFood ativa: {conn}" if conn else "Cadastre conexão iFood (Hub marketplace ou API)",
    )

    if mp_mode == "http":
        token_ok = bool((getattr(settings, "IFOOD_API_TOKEN", "") or "").strip()) or bool(
            conn and (conn.settings or {}).get("access_token")
        )
        add(
            "PILOT-10-IFOOD-HTTP",
            token_ok and bool((getattr(settings, "IFOOD_API_BASE_URL", "") or "").strip()),
            f"MARKETPLACE_HTTP_MODE=http — token e base URL",
        )
    else:
        stub_ok = bool(conn and (conn.settings or {}).get("stub_orders"))
        add(
            "PILOT-10-MARKETPLACE-MODE",
            True,
            f"MARKETPLACE_HTTP_MODE={mp_mode}"
            + (" + stub_orders na conexão" if stub_ok else " (HTTP iFood quando sandbox contratado)"),
            required=False,
        )

    mapped = FoodProduct.objects.filter(
        tenant=tenant, is_active=True, nfe_product__isnull=False
    ).count()
    add(
        "PILOT-11-PRODUCT-MAP",
        mapped >= 1,
        f"{mapped} produto(s) Food com de-para NFC-e",
    )

    for task_name, label in (
        ("food.sync_marketplace_orders", "PILOT-12-BEAT-SYNC"),
        ("food.reconcile_ifood_fiscal", "PILOT-13-BEAT-RECONCILE"),
        ("nfce.reconcile_stale", "PILOT-14-BEAT-NFCE"),
    ):
        spec = _beat_task(task_name)
        add(
            label,
            spec is not None,
            f"Celery beat {task_name} schedule={spec.get('schedule') if spec else 'ausente'}",
        )

    ifood_orders = FoodOrder.objects.filter(
        tenant=tenant, channel=FoodOrder.Channel.IFOOD
    ).count()
    add(
        "PILOT-15-ORDERS",
        ifood_orders >= 0,
        f"{ifood_orders} pedido(s) iFood no tenant (smoke: importe >=1 antes do go-live)",
        required=False,
    )

    hosts = [h.strip() for h in (getattr(settings, "ALLOWED_HOSTS", []) or []) if h.strip()]
    lab_only = set(hosts) <= {"localhost", "127.0.0.1", "testserver"}
    add(
        "PILOT-16-ALLOWED-HOSTS",
        (not lab_only) if strict_prod else True,
        f"ALLOWED_HOSTS={hosts}",
        required=strict_prod,
    )

    nfce_mode = (getattr(settings, "NFCE_HTTP_MODE", "stub") or "stub").lower()
    add(
        "PILOT-17-NFCE-MODE",
        True,
        f"NFCE_HTTP_MODE={nfce_mode} (stub homolog | http produção parceiro/SEFAZ)",
        required=False,
    )

    failed_required = [c for c in checks if c["required"] and not c["ok"]]
    kpis = compute_ifood_fiscal_piloto_kpis(tenant_id=tenant.id)

    return {
        "tenant_slug": tenant.slug,
        "tenant_id": str(tenant.id),
        "strict_prod": strict_prod,
        "summary": {
            "pass": sum(1 for c in checks if c["ok"]),
            "fail": sum(1 for c in checks if not c["ok"]),
            "fail_required": len(failed_required),
            "total": len(checks),
        },
        "checks": checks,
        "kpis_7d": kpis,
        "hub_urls": {
            "orders": "/hub/food/pedidos/",
            "ifood_fiscal": "/hub/food/pedidos/ifood-fiscal/",
            "marketplace": "/hub/food/marketplace/",
            "products": "/hub/food/produtos/",
        },
        "next_steps": _next_steps(checks, conn=conn, mp_mode=mp_mode),
        "ready_for_pilot": len(failed_required) == 0,
    }


def _next_steps(
    checks: list[dict[str, Any]],
    *,
    conn: FoodMarketplaceConnection | None,
    mp_mode: str,
) -> list[str]:
    by_id = {c["id"]: c for c in checks}
    steps: list[str] = []
    if not by_id.get("PILOT-05-TENANT-NFCE", {}).get("ok"):
        steps.append("Admin tenant: habilitar emissão NFC-e (nfce_enabled).")
    if not by_id.get("PILOT-07-PROVIDER", {}).get("ok"):
        steps.append("Cadastrar emitente SP ativo (master_data Provider) + certificado A1.")
    if not by_id.get("PILOT-09-IFOOD-CONNECTION", {}).get("ok"):
        steps.append("Hub -> Marketplace: criar conexao iFood (merchant_ref + provider_id).")
    if not by_id.get("PILOT-11-PRODUCT-MAP", {}).get("ok"):
        steps.append("Hub -> Produtos: vincular NfeProduct (de-para) para SKUs do cardapio.")
    if mp_mode == "stub" and conn and not (conn.settings or {}).get("stub_orders"):
        steps.append("Lab: adicionar stub_orders na conexao ou sync manual via API.")
    if mp_mode == "http":
        steps.append("Producao: IFOOD_API_* no .env + token na conexao; MARKETPLACE_HTTP_MODE=http.")
    steps.append("Ops: celery worker + celery beat com beat schedule food/nfce reconcile.")
    steps.append("Smoke: importar pedido -> fila Fiscal iFood -> emitir lote -> verificar NFC-e.")
    steps.append("Monitor: logs exeq.food.fiscal + KPIs via ifood_fiscal_piloto_evidence.")
    return steps
