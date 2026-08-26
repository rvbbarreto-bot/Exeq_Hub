"""Hub V4 UI — EXEQ Hub Food (pedidos + operação + inteligência)."""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.accounts.permissions import FOOD_WRITE_ROLES
from apps.food.exceptions import FoodError, FoodPaymentEmailRequiredError, FoodPaymentCardTokenRequiredError
from apps.food.intelligence import intelligence_report
from apps.food.models import (
    FoodCustomer,
    FoodMarketplaceConnection,
    FoodOrder,
    FoodProduct,
    FoodProductionOrder,
    FoodPurchase,
    FoodRetentionDispatch,
    FoodRetentionEnrollment,
    FoodRetentionRule,
    FoodSupplier,
)
from apps.food.operations import (
    ORDER_TRANSITIONS,
    create_purchase,
    create_supplier,
    receive_purchase,
    sync_marketplace_connection,
    transition_order_status,
    upsert_marketplace_connection,
)
from apps.food.production import (
    complete_production,
    create_production_order,
    start_production,
)
from apps.food.retention import create_retention_rule, process_retention_tick
from apps.food.payments.display import payment_panel_context
from apps.food.payments.services import create_payment_intent_for_order
from apps.food.services import (
    create_food_customer,
    create_food_product,
    create_order,
)
from apps.food.hub_forms import parse_order_lines
from apps.food.hub_pilot import block_if_out_of_pilot
from apps.hub_v4.auth import require_hub


class FoodPilotSectionMixin:
    """Responde 404 com página explicativa para telas Hub fora do piloto."""

    pilot_section: str = ""

    def dispatch(self, request, *args, **kwargs):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        blocked = block_if_out_of_pilot(request, self.pilot_section, role=role)
        if blocked:
            return blocked
        return super().dispatch(request, *args, **kwargs)


def _food_ctx(role, **extra):
    base = {
        "nav": "food",
        "role_code": role,
        "can_write": role in FOOD_WRITE_ROLES,
        "food_section": extra.pop("food_section", "orders"),
    }
    base.update(extra)
    return base


def _require_food_hub(request: HttpRequest):
    return require_hub(request, allow_food_only=True)


def _require_food_writer_hub(request: HttpRequest):
    tenant, user, role, redir = _require_food_hub(request)
    if redir:
        return None, None, None, redir
    if role not in FOOD_WRITE_ROLES:
        messages.error(request, "Seu papel não permite editar no Food.")
        return tenant, user, role, redirect("hub-v4-food-orders")
    return tenant, user, role, None


class FoodOrdersListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        qs = (
            FoodOrder.objects.filter(tenant=tenant)
            .select_related("customer", "charge")
            .order_by("-created_at")
        )
        status_f = (request.GET.get("status") or "").strip()
        if status_f:
            qs = qs.filter(status=status_f)
        page = Paginator(qs, 20).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/food/orders_list.html",
            _food_ctx(
                role,
                food_section="orders",
                page_title="Pedidos Food",
                page=page,
                status_choices=FoodOrder.Status.choices,
                status_filter=status_f,
            ),
        )


class FoodOrderDetailView(View):
    template_name = "food/order_detail.html"

    def _order_qs(self, tenant):
        return (
            FoodOrder.objects.filter(tenant=tenant)
            .select_related("customer", "charge", "coupon")
            .prefetch_related("lines", "payments__events")
        )

    def get(self, request: HttpRequest, pk):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        order = get_object_or_404(self._order_qs(tenant), pk=pk)
        next_statuses = sorted(ORDER_TRANSITIONS.get(order.status, set()))
        status_labels = dict(FoodOrder.Status.choices)
        panel = payment_panel_context(tenant=tenant, order=order)
        return render(
            request,
            self.template_name,
            _food_ctx(
                role,
                food_section="orders",
                page_title=f"Pedido {str(order.id)[:8]}…",
                order=order,
                next_status_choices=[
                    (s, status_labels.get(s, s)) for s in next_statuses
                ],
                **panel,
            ),
        )

    def post(self, request: HttpRequest, pk):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        order = get_object_or_404(FoodOrder, pk=pk, tenant=tenant)
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "pix":
                create_payment_intent_for_order(
                    tenant=tenant, order_id=order.id, method="pix"
                )
                messages.success(request, "Pagamento Pix gerado no gateway.")
            elif action == "card":
                installments_raw = (request.POST.get("installments") or "1").strip()
                try:
                    installments = max(1, int(installments_raw))
                except ValueError:
                    installments = 1
                updated = create_payment_intent_for_order(
                    tenant=tenant,
                    order_id=order.id,
                    method="card",
                    card_token=(request.POST.get("card_token") or "").strip(),
                    payment_method_id=(request.POST.get("payment_method_id") or "").strip(),
                    issuer_id=(request.POST.get("issuer_id") or "").strip(),
                    installments=installments,
                )
                if updated.payment_status == FoodOrder.PaymentStatus.PAID:
                    messages.success(request, "Pagamento com cartão aprovado.")
                elif updated.payment_status == FoodOrder.PaymentStatus.FAILED:
                    messages.error(request, "Pagamento com cartão recusado.")
                else:
                    messages.info(request, "Pagamento com cartão em processamento.")
            elif action == "transition":
                to_status = (request.POST.get("status") or "").strip()
                transition_order_status(
                    tenant=tenant, order_id=order.id, to_status=to_status
                )
                messages.success(request, f"Status atualizado para {to_status}.")
            elif action == "customer_email":
                email = (request.POST.get("customer_email") or "").strip()
                customer = order.customer
                customer.email = email
                customer.save(update_fields=["email", "updated_at"])
                messages.success(request, "E-mail do cliente atualizado.")
        except FoodPaymentEmailRequiredError as exc:
            messages.error(
                request,
                f"{exc} Cadastre o e-mail do cliente e tente novamente.",
            )
        except FoodPaymentCardTokenRequiredError as exc:
            messages.error(request, str(exc))
        except FoodError as exc:
            messages.error(request, str(exc))
        return redirect("hub-v4-food-order-detail", pk=order.id)


class FoodOrderCreateView(View):
    template_name = "hub_v4/food/order_form.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        return render(request, self.template_name, self._ctx(tenant, role))

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        try:
            order = self._create(request, tenant)
        except (FoodError, ValueError) as exc:
            messages.error(request, str(exc) or "Falha ao criar pedido.")
            return render(
                request,
                self.template_name,
                {**self._ctx(tenant, role), "form": request.POST},
            )
        messages.success(request, "Pedido criado.")
        return redirect("hub-v4-food-order-detail", pk=order.id)

    def _ctx(self, tenant, role):
        return _food_ctx(
            role,
            food_section="orders",
            page_title="Novo pedido Food",
            customers=FoodCustomer.objects.filter(
                tenant=tenant, is_active=True
            ).order_by("name")[:300],
            products=FoodProduct.objects.filter(tenant=tenant, is_active=True).order_by(
                "sku"
            )[:300],
            channels=FoodOrder.Channel.choices,
            idempotency_key=f"hub-food-{uuid.uuid4()}",
        )

    def _create(self, request, tenant):
        customer_id = request.POST.get("customer_id")
        if not customer_id:
            raise ValueError("Cliente é obrigatório.")
        lines = parse_order_lines(request.POST)

        new_name = (request.POST.get("new_customer_name") or "").strip()
        if customer_id == "__new__" and new_name:
            phone = (request.POST.get("new_customer_phone") or "").strip()
            doc = (request.POST.get("new_customer_document") or "").strip()
            email = (request.POST.get("new_customer_email") or "").strip()
            customer = create_food_customer(
                tenant=tenant,
                name=new_name,
                phone_e164=phone,
                document=doc,
                email=email,
            )
            customer_id = customer.id

        await_pix = (request.POST.get("await_pix") or "1") == "1"
        request_pix = (request.POST.get("request_pix") or "") == "1"
        order = create_order(
            tenant=tenant,
            customer_id=customer_id,
            channel=request.POST.get("channel") or FoodOrder.Channel.COUNTER,
            lines=lines,
            idempotency_key=request.POST.get("idempotency_key")
            or f"hub-food-{uuid.uuid4()}",
            notes=request.POST.get("notes") or "",
            await_pix=await_pix,
            deduct_stock=not await_pix,
        )
        if request_pix and order.payment_status != FoodOrder.PaymentStatus.PAID:
            order = create_payment_intent_for_order(
                tenant=tenant, order_id=order.id, method="pix"
            )
        return order


class FoodProductsListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        qs = FoodProduct.objects.filter(tenant=tenant).order_by("sku")
        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
        page = Paginator(qs, 30).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/food/products_list.html",
            _food_ctx(
                role,
                food_section="products",
                page_title="Produtos Food",
                page=page,
                search_q=q,
            ),
        )


class FoodProductCreateView(View):
    template_name = "hub_v4/food/product_form.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        return render(request, self.template_name, self._ctx(role))

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        try:
            price_cents = _parse_money_to_cents(request.POST.get("price") or "0")
            cost_cents = _parse_money_to_cents(request.POST.get("cost") or "0")
            create_food_product(
                tenant=tenant,
                sku=(request.POST.get("sku") or "").strip(),
                name=(request.POST.get("name") or "").strip(),
                price_cents=price_cents,
                cost_cents=cost_cents,
                category=(request.POST.get("category") or "").strip(),
                unit=(request.POST.get("unit") or "un").strip() or "un",
                initial_stock=(request.POST.get("initial_stock") or "0").replace(",", "."),
            )
        except (FoodError, ValueError) as exc:
            messages.error(request, str(exc) or "Falha ao cadastrar produto.")
            return render(
                request,
                self.template_name,
                {**self._ctx(role), "form": request.POST},
            )
        messages.success(request, "Produto cadastrado.")
        return redirect("hub-v4-food-products")

    def _ctx(self, role):
        return _food_ctx(role, food_section="products", page_title="Novo produto Food")


class FoodCustomersListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        qs = FoodCustomer.objects.filter(tenant=tenant, is_active=True).order_by("name")
        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        page = Paginator(qs, 30).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/food/customers_list.html",
            _food_ctx(
                role,
                food_section="customers",
                page_title="Clientes Food",
                page=page,
                search_q=q,
            ),
        )


class FoodCustomerCreateView(View):
    template_name = "hub_v4/food/customer_form.html"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        return render(request, self.template_name, self._ctx(role))

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        try:
            create_food_customer(
                tenant=tenant,
                name=(request.POST.get("name") or "").strip(),
                phone_e164=(request.POST.get("phone_e164") or "").strip(),
                email=(request.POST.get("email") or "").strip(),
                document=(request.POST.get("document") or "").strip(),
            )
        except (FoodError, ValueError) as exc:
            messages.error(request, str(exc) or "Falha ao cadastrar cliente.")
            return render(
                request,
                self.template_name,
                {**self._ctx(role), "form": request.POST},
            )
        messages.success(request, "Cliente cadastrado.")
        return redirect("hub-v4-food-customers")

    def _ctx(self, role):
        return _food_ctx(role, food_section="customers", page_title="Novo cliente Food")


def _parse_money_to_cents(raw: str) -> int:
    """Aceita centavos inteiros (\"700\") ou reais com decimal (\"7,00\" / \"7.00\")."""
    s = (raw or "").strip()
    if not s:
        return 0
    if "," in s or "." in s:
        if "," in s and "." in s:
            # 1.234,56 → remove milhar, vírgula decimal
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        return int((Decimal(s) * 100).quantize(Decimal("1")))
    return int(s)


def _create_purchase_from_post(*, tenant, post) -> None:
    supplier_id = post.get("supplier_id")
    if supplier_id == "__new__":
        supplier = create_supplier(
            tenant=tenant,
            name=(post.get("supplier_name") or "").strip() or "Fornecedor",
            document=post.get("supplier_document") or "",
        )
        supplier_id = supplier.id
    product_id = post.get("product_id")
    if not supplier_id or not product_id:
        raise ValueError("Fornecedor e produto são obrigatórios.")
    qty = Decimal((post.get("quantity") or "1").replace(",", "."))
    create_purchase(
        tenant=tenant,
        supplier_id=supplier_id,
        lines=[
            {
                "product_id": product_id,
                "quantity": qty,
                "unit_cost_cents": _parse_money_to_cents(post.get("unit_cost") or "0"),
            }
        ],
        idempotency_key=post.get("idempotency_key") or f"hub-purch-{uuid.uuid4()}",
    )


class FoodPurchasesListView(FoodPilotSectionMixin, View):
    pilot_section = "purchases"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        qs = (
            FoodPurchase.objects.filter(tenant=tenant)
            .select_related("supplier")
            .order_by("-created_at")
        )
        page = Paginator(qs, 20).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/food/purchases_list.html",
            _food_ctx(
                role,
                food_section="purchases",
                page_title="Compras Food",
                page=page,
            ),
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "receive":
                receive_purchase(
                    tenant=tenant, purchase_id=request.POST.get("purchase_id")
                )
                messages.success(request, "Compra recebida; estoque atualizado.")
            elif action == "create":
                _create_purchase_from_post(tenant=tenant, post=request.POST)
                messages.success(request, "Compra registrada.")
        except (FoodError, ValueError, InvalidOperation) as exc:
            messages.error(request, str(exc))
        return redirect("hub-v4-food-purchases")


class FoodPurchasesNewView(FoodPilotSectionMixin, View):
    pilot_section = "purchases"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        return render(
            request,
            "hub_v4/food/purchase_form.html",
            _food_ctx(
                role,
                food_section="purchases",
                page_title="Nova compra",
                suppliers=FoodSupplier.objects.filter(
                    tenant=tenant, is_active=True
                ).order_by("name")[:200],
                products=FoodProduct.objects.filter(
                    tenant=tenant, is_active=True
                ).order_by("sku")[:300],
                idempotency_key=f"hub-purch-{uuid.uuid4()}",
            ),
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        try:
            _create_purchase_from_post(tenant=tenant, post=request.POST)
            messages.success(request, "Compra registrada.")
            return redirect("hub-v4-food-purchases")
        except (FoodError, ValueError, InvalidOperation) as exc:
            messages.error(request, str(exc))
            return render(
                request,
                "hub_v4/food/purchase_form.html",
                {
                    **_food_ctx(
                        role,
                        food_section="purchases",
                        page_title="Nova compra",
                        suppliers=FoodSupplier.objects.filter(
                            tenant=tenant, is_active=True
                        ).order_by("name")[:200],
                        products=FoodProduct.objects.filter(
                            tenant=tenant, is_active=True
                        ).order_by("sku")[:300],
                        idempotency_key=request.POST.get("idempotency_key")
                        or f"hub-purch-{uuid.uuid4()}",
                    ),
                    "form": request.POST,
                },
            )


class FoodProductionListView(View):
    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        qs = (
            FoodProductionOrder.objects.filter(tenant=tenant)
            .select_related("product", "bom")
            .order_by("-created_at")
        )
        page = Paginator(qs, 20).get_page(request.GET.get("page") or 1)
        return render(
            request,
            "hub_v4/food/production_list.html",
            _food_ctx(
                role,
                food_section="production",
                page_title="Produção Food",
                page=page,
                products=FoodProduct.objects.filter(
                    tenant=tenant, is_active=True
                ).order_by("sku")[:300],
            ),
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "start":
                start_production(
                    tenant=tenant,
                    production_order_id=request.POST.get("production_id"),
                )
                messages.success(request, "OP iniciada; insumos baixados.")
            elif action == "complete":
                complete_production(
                    tenant=tenant,
                    production_order_id=request.POST.get("production_id"),
                )
                messages.success(request, "OP concluída; acabado no estoque.")
            elif action == "create":
                create_production_order(
                    tenant=tenant,
                    product_id=request.POST.get("product_id"),
                    quantity_planned=Decimal(
                        (request.POST.get("quantity") or "1").replace(",", ".")
                    ),
                    idempotency_key=request.POST.get("idempotency_key")
                    or f"hub-op-{uuid.uuid4()}",
                )
                messages.success(request, "Ordem de produção criada.")
        except (FoodError, ValueError, InvalidOperation) as exc:
            messages.error(request, str(exc))
        return redirect("hub-v4-food-production")


class FoodIntelligenceView(FoodPilotSectionMixin, View):
    pilot_section = "intelligence"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        lookback = int(request.GET.get("lookback_days") or 28)
        horizon = int(request.GET.get("horizon_days") or 7)
        report = intelligence_report(
            tenant=tenant, lookback_days=lookback, horizon_days=horizon
        )
        return render(
            request,
            "hub_v4/food/intelligence.html",
            _food_ctx(
                role,
                food_section="intelligence",
                page_title="Inteligência Food",
                report=report,
                lookback_days=lookback,
                horizon_days=horizon,
            ),
        )


class FoodRetentionHubView(FoodPilotSectionMixin, View):
    pilot_section = "retention"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        rules = (
            FoodRetentionRule.objects.filter(tenant=tenant)
            .prefetch_related("steps")
            .order_by("name")
        )
        enrollments = (
            FoodRetentionEnrollment.objects.filter(tenant=tenant)
            .select_related("customer", "rule")
            .order_by("-enrolled_at")[:50]
        )
        dispatches = (
            FoodRetentionDispatch.objects.filter(tenant=tenant)
            .select_related("enrollment__customer", "step", "enrollment__rule")
            .order_by("-fired_at")[:50]
        )
        return render(
            request,
            "hub_v4/food/retention.html",
            _food_ctx(
                role,
                food_section="retention",
                page_title="Régua Food",
                rules=rules,
                enrollments=enrollments,
                dispatches=dispatches,
                kind_choices=FoodRetentionRule.Kind.choices,
            ),
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "tick":
                result = process_retention_tick(tenant=tenant)
                messages.success(
                    request,
                    f"Tick: enroll={result.get('enrolled', 0)} "
                    f"fired={result.get('fired', 0)}",
                )
            elif action == "create_rule":
                steps_raw = (request.POST.get("steps_text") or "").strip()
                steps = []
                if steps_raw:
                    for i, line in enumerate(steps_raw.splitlines(), start=1):
                        line = line.strip()
                        if not line:
                            continue
                        # delay|mensagem
                        if "|" in line:
                            delay_s, msg = line.split("|", 1)
                        else:
                            delay_s, msg = "0", line
                        steps.append(
                            {
                                "sequence": i,
                                "delay_days": int(delay_s.strip() or 0),
                                "message_template": msg.strip(),
                                "channel": "whatsapp",
                            }
                        )
                else:
                    steps = [
                        {
                            "sequence": 1,
                            "delay_days": 0,
                            "message_template": (
                                "Oi {name}, sentimos sua falta! Volte e use o cupom."
                            ),
                            "channel": "whatsapp",
                        }
                    ]
                create_retention_rule(
                    tenant=tenant,
                    name=(request.POST.get("name") or "").strip(),
                    kind=request.POST.get("kind") or FoodRetentionRule.Kind.INACTIVITY,
                    steps=steps,
                    inactivity_days=int(request.POST.get("inactivity_days") or 30),
                    min_order_count=int(request.POST.get("min_order_count") or 0),
                    min_avg_ticket_cents=int(
                        request.POST.get("min_avg_ticket_cents") or 0
                    ),
                )
                messages.success(request, "Régua criada.")
            elif action == "toggle":
                rule = get_object_or_404(
                    FoodRetentionRule,
                    pk=request.POST.get("rule_id"),
                    tenant=tenant,
                )
                rule.is_active = not rule.is_active
                rule.save(update_fields=["is_active", "updated_at"])
                messages.success(
                    request,
                    f"Régua {'ativada' if rule.is_active else 'pausada'}.",
                )
        except (FoodError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("hub-v4-food-retention")


class FoodMarketplaceHubView(FoodPilotSectionMixin, View):
    pilot_section = "marketplace"

    def get(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_hub(request)
        if redir:
            return redir
        conns = FoodMarketplaceConnection.objects.filter(tenant=tenant).order_by(
            "provider", "merchant_ref"
        )
        recent = (
            FoodOrder.objects.filter(
                tenant=tenant,
                channel__in=[FoodOrder.Channel.IFOOD, FoodOrder.Channel.AIQFOME],
            )
            .select_related("customer")
            .order_by("-created_at")[:30]
        )
        return render(
            request,
            "hub_v4/food/marketplace.html",
            _food_ctx(
                role,
                food_section="marketplace",
                page_title="Marketplace Food",
                connections=conns,
                recent_orders=recent,
                provider_choices=FoodMarketplaceConnection.Provider.choices,
            ),
        )

    def post(self, request: HttpRequest):
        tenant, user, role, redir = _require_food_writer_hub(request)
        if redir:
            return redir
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "upsert":
                provider = request.POST.get("provider") or "ifood"
                merchant_ref = (request.POST.get("merchant_ref") or "").strip()
                existing = FoodMarketplaceConnection.objects.filter(
                    tenant=tenant,
                    provider=provider,
                    merchant_ref=merchant_ref,
                ).first()
                settings_blob = dict(existing.settings or {}) if existing else {}
                token = (request.POST.get("access_token") or "").strip()
                base_url = (request.POST.get("base_url") or "").strip()
                if token:
                    settings_blob["access_token"] = token
                if base_url:
                    settings_blob["base_url"] = base_url
                mode = (request.POST.get("http_mode") or "").strip()
                if mode in {"stub", "http"}:
                    settings_blob["http_mode"] = mode
                upsert_marketplace_connection(
                    tenant=tenant,
                    provider=provider,
                    merchant_ref=merchant_ref,
                    is_active=(request.POST.get("is_active") or "1") == "1",
                    settings=settings_blob,
                )
                messages.success(request, "Conexão marketplace salva.")
            elif action == "sync":
                stats = sync_marketplace_connection(
                    tenant=tenant, connection_id=request.POST.get("connection_id")
                )
                messages.success(
                    request,
                    f"Sync {stats['provider']}: "
                    f"fetched={stats['fetched']} imported={stats['imported']} "
                    f"skipped={stats['skipped']} errors={len(stats['errors'])}",
                )
                if stats["errors"]:
                    messages.warning(
                        request, f"Detalhe: {stats['errors'][0].get('message', '')}"
                    )
            elif action == "sync_all":
                from apps.food.operations import sync_all_marketplace_connections

                results = sync_all_marketplace_connections(tenant=tenant)
                total_imp = sum(r.get("imported", 0) for r in results)
                messages.success(
                    request,
                    f"Sync completo: {len(results)} conexões, {total_imp} importados.",
                )
        except FoodError as exc:
            messages.error(request, str(exc))
        return redirect("hub-v4-food-marketplace")
