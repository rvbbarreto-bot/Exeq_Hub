from celery import shared_task


@shared_task(name="food.process_retention_tick")
def process_retention_tick_task():
    """Varre tenants com régua ativa e processa enroll + disparos Food."""
    from apps.accounts.models import Tenant
    from apps.food.models import FoodRetentionRule
    from apps.food.retention import process_retention_tick

    tenant_ids = (
        FoodRetentionRule.objects.filter(is_active=True)
        .values_list("tenant_id", flat=True)
        .distinct()
    )
    results = []
    for tid in tenant_ids:
        tenant = Tenant.objects.filter(pk=tid).first()
        if tenant is None:
            continue
        results.append({"tenant": str(tid), **process_retention_tick(tenant=tenant)})
    return results


@shared_task(name="food.sync_marketplace_orders")
def sync_marketplace_orders_task():
    """Puxa pedidos de conexões marketplace ativas (stub ou HTTP)."""
    from apps.accounts.models import Tenant
    from apps.food.models import FoodMarketplaceConnection
    from apps.food.operations import sync_marketplace_connection

    pairs = FoodMarketplaceConnection.objects.filter(is_active=True).values_list(
        "tenant_id", "id"
    )
    results = []
    for tid, cid in pairs:
        tenant = Tenant.objects.filter(pk=tid).first()
        if tenant is None:
            continue
        results.append(sync_marketplace_connection(tenant=tenant, connection_id=cid))
    return results
