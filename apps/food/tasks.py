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


@shared_task(name="food.emit_ifood_batch")
def emit_food_ifood_batch_task(tenant_id: str, order_ids: list[str], *, actor: str = "celery"):
    from apps.accounts.models import Tenant
    from apps.food.fiscal.emit import emit_food_orders_batch
    from apps.food.models import FoodOrder

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return {"error": "tenant_not_found", "tenant_id": tenant_id}

    scoped = list(
        FoodOrder.objects.filter(
            tenant=tenant,
            pk__in=order_ids,
            channel=FoodOrder.Channel.IFOOD,
        ).values_list("pk", flat=True)
    )
    rejected = len(order_ids) - len(scoped)
    result = emit_food_orders_batch(
        tenant=tenant,
        order_ids=[str(x) for x in scoped],
        actor=actor,
    )
    if rejected:
        result["rejected_cross_tenant"] = rejected
    return result


@shared_task(name="food.reconcile_ifood_fiscal")
def reconcile_food_ifood_fiscal_task(limit: int = 50):
    from apps.food.fiscal.reconcile import reconcile_stale_food_fiscal_processing

    return reconcile_stale_food_fiscal_processing(limit=limit)
