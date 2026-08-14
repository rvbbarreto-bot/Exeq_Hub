from django.db import models
from django.db.models import Q

from shared.tenancy import TenantOwnedModel


class FoodCustomer(TenantOwnedModel):
    """Cliente comercial Food (telefone-first). Não substitui tomador fiscal."""

    name = models.CharField(max_length=255, verbose_name="Nome")
    phone_e164 = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="WhatsApp/telefone (E.164)",
    )
    email = models.EmailField(blank=True, default="", verbose_name="E-mail")
    document = models.CharField(
        max_length=14, blank=True, default="", verbose_name="CPF/CNPJ"
    )
    fiscal_customer = models.ForeignKey(
        "master_data.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="food_profiles",
        verbose_name="Tomador fiscal (opcional)",
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    last_order_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Última compra"
    )
    order_count = models.PositiveIntegerField(default=0, verbose_name="Qtd. pedidos")
    total_spent_cents = models.BigIntegerField(
        default=0, verbose_name="Receita acumulada (centavos)"
    )
    avg_ticket_cents = models.BigIntegerField(
        default=0, verbose_name="Ticket médio (centavos)"
    )

    class Meta:
        verbose_name = "Cliente Food"
        verbose_name_plural = "Clientes Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "phone_e164"],
                condition=~Q(phone_e164=""),
                name="uq_food_customer_tenant_phone",
            ),
            models.CheckConstraint(
                condition=Q(total_spent_cents__gte=0) & Q(avg_ticket_cents__gte=0),
                name="ck_food_customer_money_nonneg",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "last_order_at"]),
        ]

    def __str__(self) -> str:
        return self.name


class FoodProduct(TenantOwnedModel):
    sku = models.CharField(max_length=64, verbose_name="SKU")
    name = models.CharField(max_length=255, verbose_name="Nome")
    category = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Categoria"
    )
    unit = models.CharField(max_length=16, default="un", verbose_name="Unidade")
    price_cents = models.BigIntegerField(default=0, verbose_name="Preço (centavos)")
    cost_cents = models.BigIntegerField(default=0, verbose_name="Custo (centavos)")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Produto Food"
        verbose_name_plural = "Produtos Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sku"],
                name="uq_food_product_tenant_sku",
            ),
            models.CheckConstraint(
                condition=Q(price_cents__gte=0) & Q(cost_cents__gte=0),
                name="ck_food_product_money_nonneg",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "category"]),
        ]

    def __str__(self) -> str:
        return f"{self.sku} — {self.name}"


class FoodOrder(TenantOwnedModel):
    """Pedido unificado multi-canal (Order Service). Canal é atributo, não entidade."""

    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        COUNTER = "counter", "Balcão"
        IFOOD = "ifood", "iFood"
        AIQFOME = "aiqfome", "aiqfome"
        OTHER = "other", "Outro"

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PENDING_PAYMENT = "pending_payment", "Aguardando pagamento"
        CONFIRMED = "confirmed", "Confirmado"
        PREPARING = "preparing", "Em preparo"
        READY = "ready", "Pronto"
        FULFILLED = "fulfilled", "Entregue/concluído"
        CANCELLED = "cancelled", "Cancelado"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Não pago"
        AWAITING_PIX = "awaiting_pix", "Pix pendente"
        AWAITING_PAYMENT = "awaiting_payment", "Pagamento pendente"
        PAID = "paid", "Pago"
        FAILED = "failed", "Falhou"
        REFUNDED = "refunded", "Estornado"

    class FulfillmentMode(models.TextChoices):
        PICKUP = "pickup", "Retirada"
        DELIVERY = "delivery", "Delivery"
        COUNTER = "counter", "Balcão"

    customer = models.ForeignKey(
        FoodCustomer,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Cliente",
    )
    channel = models.CharField(
        max_length=16,
        choices=Channel.choices,
        verbose_name="Canal",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Status",
    )
    payment_status = models.CharField(
        max_length=16,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        verbose_name="Status pagamento",
    )
    fulfillment_mode = models.CharField(
        max_length=16,
        choices=FulfillmentMode.choices,
        default=FulfillmentMode.PICKUP,
        verbose_name="Modo de atendimento",
    )
    delivery_address = models.TextField(
        blank=True, default="", verbose_name="Endereço de entrega"
    )
    marketplace_connection = models.ForeignKey(
        "food.FoodMarketplaceConnection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Conexão marketplace",
    )
    subtotal_cents = models.BigIntegerField(default=0, verbose_name="Subtotal")
    discount_cents = models.BigIntegerField(default=0, verbose_name="Desconto")
    total_cents = models.BigIntegerField(default=0, verbose_name="Total")
    notes = models.TextField(blank=True, default="", verbose_name="Observações")
    idempotency_key = models.CharField(
        max_length=128, verbose_name="Chave de idempotência"
    )
    pix_txid = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Pix txid"
    )
    charge = models.ForeignKey(
        "billing.Charge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="food_orders",
        verbose_name="Cobrança (Pix/boleto)",
    )
    coupon = models.ForeignKey(
        "food.FoodCoupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Cupom aplicado",
    )
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Pago em")
    channel_ref = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="Ref. canal (ex. message id)",
    )

    class Meta:
        verbose_name = "Pedido Food"
        verbose_name_plural = "Pedidos Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_food_order_tenant_idempotency",
            ),
            models.CheckConstraint(
                condition=Q(subtotal_cents__gte=0)
                & Q(discount_cents__gte=0)
                & Q(total_cents__gte=0)
                & Q(discount_cents__lte=models.F("subtotal_cents")),
                name="ck_food_order_money",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "channel"]),
            models.Index(fields=["tenant", "payment_status"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "charge"]),
        ]

    def __str__(self) -> str:
        return f"Pedido {self.id} ({self.channel}/{self.status})"


class FoodPayment(TenantOwnedModel):
    """Pagamento nativo Food (Mercado Pago e futuros PSPs). Inter usa billing.Charge."""

    class Provider(models.TextChoices):
        INTER = "inter", "Inter"
        ASAAS = "asaas", "Asaas"
        C6 = "c6", "C6"
        MERCADOPAGO = "mercadopago", "Mercado Pago"

    class Method(models.TextChoices):
        PIX = "pix", "Pix"
        CARD = "card", "Cartão"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        AWAITING_PAYMENT = "awaiting_payment", "Aguardando pagamento"
        PAID = "paid", "Pago"
        FAILED = "failed", "Falhou"
        CANCELLED = "cancelled", "Cancelado"
        EXPIRED = "expired", "Expirado"

    order = models.ForeignKey(
        FoodOrder,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Pedido",
    )
    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
        verbose_name="Provedor",
    )
    method = models.CharField(
        max_length=16,
        choices=Method.choices,
        verbose_name="Meio",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    idempotency_key = models.CharField(
        max_length=128,
        verbose_name="Chave de idempotência",
    )
    provider_payment_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="ID pagamento no provedor",
    )
    amount_cents = models.BigIntegerField(verbose_name="Valor (centavos)")
    pix_copy_paste = models.TextField(
        blank=True,
        default="",
        verbose_name="PIX copia e cola",
    )
    failure_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Código de falha",
    )
    failure_detail = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Detalhe da falha",
    )
    gateway_payload = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Payload do gateway",
    )
    charge = models.ForeignKey(
        "billing.Charge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="food_payments",
        verbose_name="Cobrança billing (Inter)",
    )
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Pago em")

    class Meta:
        verbose_name = "Pagamento Food"
        verbose_name_plural = "Pagamentos Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_food_payment_tenant_idempotency",
            ),
            models.CheckConstraint(
                condition=Q(amount_cents__gt=0),
                name="ck_food_payment_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "order", "status"]),
            models.Index(fields=["tenant", "provider_payment_id"]),
            models.Index(fields=["tenant", "provider", "status"]),
        ]

    def __str__(self) -> str:
        return f"FoodPayment {self.id} ({self.provider}/{self.method})"


class FoodPaymentEvent(TenantOwnedModel):
    """Evento de webhook/idempotência por pagamento Food."""

    payment = models.ForeignKey(
        FoodPayment,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="Pagamento",
    )
    provider = models.CharField(max_length=32, verbose_name="Provedor")
    event_id = models.CharField(max_length=128, verbose_name="ID do evento")
    payload = models.JSONField(default=dict, blank=True, verbose_name="Payload")

    class Meta:
        verbose_name = "Evento pagamento Food"
        verbose_name_plural = "Eventos pagamento Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "event_id"],
                name="uq_food_payment_event_tenant_provider_event",
            ),
        ]


class FoodOrderLine(TenantOwnedModel):
    order = models.ForeignKey(
        FoodOrder,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Pedido",
    )
    product = models.ForeignKey(
        FoodProduct,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_lines",
        verbose_name="Produto",
    )
    sku = models.CharField(max_length=64, verbose_name="SKU (snapshot)")
    name = models.CharField(max_length=255, verbose_name="Nome (snapshot)")
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Quantidade"
    )
    unit = models.CharField(max_length=16, default="un", verbose_name="Unidade")
    unit_price_cents = models.BigIntegerField(verbose_name="Preço unitário")
    line_total_cents = models.BigIntegerField(verbose_name="Total da linha")

    class Meta:
        verbose_name = "Item do pedido Food"
        verbose_name_plural = "Itens do pedido Food"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0)
                & Q(unit_price_cents__gte=0)
                & Q(line_total_cents__gte=0),
                name="ck_food_order_line_values",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "order"]),
        ]

    def __str__(self) -> str:
        return f"{self.sku} x {self.quantity}"


class FoodStockBalance(TenantOwnedModel):
    """Saldo físico + reserva (disponível = quantity - reserved_quantity)."""

    product = models.OneToOneField(
        FoodProduct,
        on_delete=models.CASCADE,
        related_name="stock_balance",
        verbose_name="Produto",
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, verbose_name="Saldo físico"
    )
    reserved_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name="Reservado",
    )
    min_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name="Mínimo (alerta)",
    )

    class Meta:
        verbose_name = "Estoque Food"
        verbose_name_plural = "Estoques Food"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gte=0) & Q(reserved_quantity__gte=0),
                name="ck_food_stock_nonneg",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "quantity"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}: {self.quantity}"

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity

    @property
    def is_below_min(self) -> bool:
        return self.available_quantity < self.min_quantity


class FoodStockMovement(TenantOwnedModel):
    class MovementType(models.TextChoices):
        IN = "in", "Entrada"
        OUT = "out", "Saída"
        ADJUST = "adjust", "Ajuste"

    product = models.ForeignKey(
        FoodProduct,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        verbose_name="Produto",
    )
    movement_type = models.CharField(
        max_length=16,
        choices=MovementType.choices,
        verbose_name="Tipo",
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name="Quantidade"
    )
    balance_after = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name="Saldo após"
    )
    reason = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Motivo"
    )
    order = models.ForeignKey(
        FoodOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
        verbose_name="Pedido",
    )

    class Meta:
        verbose_name = "Movimento de estoque Food"
        verbose_name_plural = "Movimentos de estoque Food"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="ck_food_stock_movement_qty_pos",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "product", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.quantity} ({self.product_id})"


class FoodCampaign(TenantOwnedModel):
    """Campanha comercial (agrupa cupons rastreados)."""

    name = models.CharField(max_length=255, verbose_name="Nome")
    code = models.SlugField(max_length=64, verbose_name="Código")
    is_active = models.BooleanField(default=True, verbose_name="Ativa")
    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="Início")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="Fim")

    class Meta:
        verbose_name = "Campanha Food"
        verbose_name_plural = "Campanhas Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="uq_food_campaign_tenant_code",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class FoodCoupon(TenantOwnedModel):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percentual"
        FIXED = "fixed_cents", "Valor fixo"

    campaign = models.ForeignKey(
        FoodCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupons",
        verbose_name="Campanha",
    )
    code = models.CharField(max_length=64, verbose_name="Código do cupom")
    discount_type = models.CharField(
        max_length=16, choices=DiscountType.choices, verbose_name="Tipo de desconto"
    )
    percent_bps = models.PositiveIntegerField(
        default=0,
        verbose_name="Percentual (basis points)",
        help_text="1000 = 10%. Usado quando tipo=percent.",
    )
    amount_cents = models.BigIntegerField(
        default=0, verbose_name="Valor fixo (centavos)"
    )
    min_order_cents = models.BigIntegerField(default=0, verbose_name="Pedido mínimo")
    max_redemptions = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Máx. resgates (null=ilimitado)"
    )
    redemption_count = models.PositiveIntegerField(
        default=0, verbose_name="Resgates realizados"
    )
    valid_from = models.DateTimeField(null=True, blank=True, verbose_name="Válido de")
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name="Válido até")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Cupom Food"
        verbose_name_plural = "Cupons Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="uq_food_coupon_tenant_code",
            ),
            models.CheckConstraint(
                condition=Q(percent_bps__lte=10000)
                & Q(amount_cents__gte=0)
                & Q(min_order_cents__gte=0),
                name="ck_food_coupon_values",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class FoodCouponRedemption(TenantOwnedModel):
    """Rastro campanha → cupom → pedido → venda."""

    coupon = models.ForeignKey(
        FoodCoupon,
        on_delete=models.PROTECT,
        related_name="redemptions",
        verbose_name="Cupom",
    )
    order = models.OneToOneField(
        FoodOrder,
        on_delete=models.PROTECT,
        related_name="coupon_redemption",
        verbose_name="Pedido",
    )
    customer = models.ForeignKey(
        FoodCustomer,
        on_delete=models.PROTECT,
        related_name="coupon_redemptions",
        verbose_name="Cliente",
    )
    campaign = models.ForeignKey(
        FoodCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redemptions",
        verbose_name="Campanha",
    )
    discount_cents = models.BigIntegerField(verbose_name="Desconto aplicado")

    class Meta:
        verbose_name = "Resgate de cupom Food"
        verbose_name_plural = "Resgates de cupom Food"
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_cents__gte=0),
                name="ck_food_coupon_redemption_nonneg",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.coupon_id}@{self.order_id}"


class FoodRetentionRule(TenantOwnedModel):
    """Régua parametrizável por tenant (nunca hardcoded no código)."""

    class Kind(models.TextChoices):
        INACTIVITY = "inactivity", "Inatividade"
        VIP = "vip", "VIP (frequência)"
        HIGH_TICKET = "high_ticket", "Alto ticket"
        CUSTOM = "custom", "Custom"

    name = models.CharField(max_length=255, verbose_name="Nome")
    kind = models.CharField(max_length=32, choices=Kind.choices, verbose_name="Tipo")
    is_active = models.BooleanField(default=True, verbose_name="Ativa")
    inactivity_days = models.PositiveIntegerField(
        default=30,
        verbose_name="Dias de inatividade",
        help_text="Usado em kind=inactivity (sem compra neste intervalo).",
    )
    min_order_count = models.PositiveIntegerField(
        default=0, verbose_name="Mín. pedidos (VIP)"
    )
    min_avg_ticket_cents = models.BigIntegerField(
        default=0, verbose_name="Ticket médio mínimo (alto ticket)"
    )

    class Meta:
        verbose_name = "Régua de retenção Food"
        verbose_name_plural = "Réguas de retenção Food"
        indexes = [
            models.Index(fields=["tenant", "is_active", "kind"]),
        ]

    def __str__(self) -> str:
        return self.name


class FoodRetentionStep(TenantOwnedModel):
    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"

    rule = models.ForeignKey(
        FoodRetentionRule,
        on_delete=models.CASCADE,
        related_name="steps",
        verbose_name="Régua",
    )
    sequence = models.PositiveSmallIntegerField(verbose_name="Ordem")
    delay_days = models.PositiveIntegerField(
        default=0,
        verbose_name="Dias após etapa anterior",
        help_text="Na 1ª etapa: dias após elegibilidade/enroll.",
    )
    channel = models.CharField(
        max_length=16,
        choices=Channel.choices,
        default=Channel.WHATSAPP,
        verbose_name="Canal",
    )
    message_template = models.TextField(
        verbose_name="Mensagem",
        help_text="Placeholders: {name}, {coupon_code}",
    )
    coupon = models.ForeignKey(
        FoodCoupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retention_steps",
        verbose_name="Cupom (opcional)",
    )

    class Meta:
        verbose_name = "Etapa de régua Food"
        verbose_name_plural = "Etapas de régua Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "rule", "sequence"],
                name="uq_food_retention_step_seq",
            ),
        ]
        ordering = ["sequence"]

    def __str__(self) -> str:
        return f"{self.rule_id}#{self.sequence}"


class FoodRetentionEnrollment(TenantOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        COMPLETED = "completed", "Concluída"
        STOPPED = "stopped", "Interrompida (comprou)"

    rule = models.ForeignKey(
        FoodRetentionRule,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="Régua",
    )
    customer = models.ForeignKey(
        FoodCustomer,
        on_delete=models.CASCADE,
        related_name="retention_enrollments",
        verbose_name="Cliente",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Status",
    )
    next_sequence = models.PositiveSmallIntegerField(
        default=1, verbose_name="Próxima etapa (sequence)"
    )
    enrolled_at = models.DateTimeField(verbose_name="Inscrito em")
    next_fire_at = models.DateTimeField(verbose_name="Próximo disparo")
    stopped_at = models.DateTimeField(null=True, blank=True, verbose_name="Parado em")
    stop_reason = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Motivo parada"
    )

    class Meta:
        verbose_name = "Inscrição régua Food"
        verbose_name_plural = "Inscrições régua Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "rule", "customer"],
                condition=Q(status="active"),
                name="uq_food_retention_enrollment_active",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "next_fire_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.customer_id}@{self.rule_id}({self.status})"


class FoodRetentionDispatch(TenantOwnedModel):
    class Status(models.TextChoices):
        SENT = "sent", "Enviado"
        SKIPPED = "skipped", "Ignorado"
        FAILED = "failed", "Falhou"

    enrollment = models.ForeignKey(
        FoodRetentionEnrollment,
        on_delete=models.CASCADE,
        related_name="dispatches",
        verbose_name="Inscrição",
    )
    step = models.ForeignKey(
        FoodRetentionStep,
        on_delete=models.PROTECT,
        related_name="dispatches",
        verbose_name="Etapa",
    )
    idempotency_key = models.CharField(max_length=160, verbose_name="Idempotência")
    status = models.CharField(
        max_length=16, choices=Status.choices, verbose_name="Status"
    )
    message_body = models.TextField(blank=True, default="", verbose_name="Mensagem")
    channel_notification = models.ForeignKey(
        "channel.ChannelNotification",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="food_retention_dispatches",
        verbose_name="Notificação canal",
    )
    fired_at = models.DateTimeField(verbose_name="Disparado em")

    class Meta:
        verbose_name = "Disparo régua Food"
        verbose_name_plural = "Disparos régua Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_food_retention_dispatch_idem",
            ),
        ]

    def __str__(self) -> str:
        return self.idempotency_key


class FoodSupplier(TenantOwnedModel):
    name = models.CharField(max_length=255, verbose_name="Nome")
    document = models.CharField(
        max_length=14, blank=True, default="", verbose_name="CNPJ/CPF"
    )
    phone = models.CharField(max_length=32, blank=True, default="", verbose_name="Telefone")
    email = models.EmailField(blank=True, default="", verbose_name="E-mail")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    notes = models.TextField(blank=True, default="", verbose_name="Observações")

    class Meta:
        verbose_name = "Fornecedor Food"
        verbose_name_plural = "Fornecedores Food"
        indexes = [models.Index(fields=["tenant", "is_active"])]

    def __str__(self) -> str:
        return self.name


class FoodPurchase(TenantOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        ORDERED = "ordered", "Pedido ao fornecedor"
        RECEIVED = "received", "Recebido"
        CANCELLED = "cancelled", "Cancelado"

    supplier = models.ForeignKey(
        FoodSupplier,
        on_delete=models.PROTECT,
        related_name="purchases",
        verbose_name="Fornecedor",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Status",
    )
    idempotency_key = models.CharField(max_length=128, verbose_name="Idempotência")
    expected_at = models.DateField(null=True, blank=True, verbose_name="Previsão")
    received_at = models.DateTimeField(null=True, blank=True, verbose_name="Recebido em")
    notes = models.TextField(blank=True, default="", verbose_name="Observações")
    total_cents = models.BigIntegerField(default=0, verbose_name="Total")

    class Meta:
        verbose_name = "Compra Food"
        verbose_name_plural = "Compras Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_food_purchase_tenant_idempotency",
            ),
            models.CheckConstraint(
                condition=Q(total_cents__gte=0),
                name="ck_food_purchase_total_nonneg",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "supplier"]),
        ]

    def __str__(self) -> str:
        return f"Compra {self.id} ({self.status})"


class FoodPurchaseLine(TenantOwnedModel):
    purchase = models.ForeignKey(
        FoodPurchase,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Compra",
    )
    product = models.ForeignKey(
        FoodProduct,
        on_delete=models.PROTECT,
        related_name="purchase_lines",
        verbose_name="Produto",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3, verbose_name="Qtd")
    unit_cost_cents = models.BigIntegerField(default=0, verbose_name="Custo unitário")
    line_total_cents = models.BigIntegerField(default=0, verbose_name="Total linha")

    class Meta:
        verbose_name = "Item de compra Food"
        verbose_name_plural = "Itens de compra Food"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0)
                & Q(unit_cost_cents__gte=0)
                & Q(line_total_cents__gte=0),
                name="ck_food_purchase_line_values",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} x {self.quantity}"


class FoodDeliveryRoute(TenantOwnedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        IN_PROGRESS = "in_progress", "Em rota"
        CLOSED = "closed", "Fechada"

    name = models.CharField(max_length=128, verbose_name="Nome")
    service_date = models.DateField(verbose_name="Data do serviço")
    driver_name = models.CharField(
        max_length=128, blank=True, default="", verbose_name="Motorista"
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "Rota de delivery Food"
        verbose_name_plural = "Rotas de delivery Food"
        indexes = [
            models.Index(fields=["tenant", "service_date", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.service_date})"


class FoodDeliveryStop(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        OUT = "out_for_delivery", "Saiu para entrega"
        DELIVERED = "delivered", "Entregue"
        FAILED = "failed", "Falha"

    route = models.ForeignKey(
        FoodDeliveryRoute,
        on_delete=models.CASCADE,
        related_name="stops",
        verbose_name="Rota",
    )
    order = models.OneToOneField(
        FoodOrder,
        on_delete=models.PROTECT,
        related_name="delivery_stop",
        verbose_name="Pedido",
    )
    sequence = models.PositiveSmallIntegerField(default=1, verbose_name="Ordem")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status",
    )
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="Entregue em")
    notes = models.CharField(max_length=255, blank=True, default="", verbose_name="Notas")

    class Meta:
        verbose_name = "Parada delivery Food"
        verbose_name_plural = "Paradas delivery Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "route", "sequence"],
                name="uq_food_delivery_stop_seq",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "route", "status"]),
        ]

    def __str__(self) -> str:
        return f"Stop {self.sequence} order={self.order_id}"


class FoodMarketplaceConnection(TenantOwnedModel):
    """Credencial/merchant marketplace. Pull via integrations.marketplace (stub|http)."""

    class Provider(models.TextChoices):
        IFOOD = "ifood", "iFood"
        AIQFOME = "aiqfome", "aiqfome"

    provider = models.CharField(
        max_length=16, choices=Provider.choices, verbose_name="Provedor"
    )
    merchant_ref = models.CharField(
        max_length=128, verbose_name="ID loja no marketplace"
    )
    is_active = models.BooleanField(default=True, verbose_name="Ativo")
    settings = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Config",
        help_text=(
            "access_token, base_url, orders_path, sku_map, stub_orders, http_mode"
        ),
    )

    class Meta:
        verbose_name = "Conexão marketplace Food"
        verbose_name_plural = "Conexões marketplace Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "merchant_ref"],
                name="uq_food_marketplace_merchant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.merchant_ref}"


class FoodBom(TenantOwnedModel):
    """Ficha técnica (BOM) do produto acabado."""

    product = models.ForeignKey(
        FoodProduct,
        on_delete=models.PROTECT,
        related_name="boms",
        verbose_name="Produto acabado",
    )
    name = models.CharField(max_length=255, verbose_name="Nome")
    is_active = models.BooleanField(default=True, verbose_name="Ativa")
    expected_yield_bps = models.PositiveIntegerField(
        default=10000,
        verbose_name="Rendimento esperado (bps)",
        help_text="10000 = 100%",
    )

    class Meta:
        verbose_name = "Ficha técnica Food"
        verbose_name_plural = "Fichas técnicas Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product"],
                condition=Q(is_active=True),
                name="uq_food_bom_active_product",
            ),
            models.CheckConstraint(
                condition=Q(expected_yield_bps__gte=1) & Q(expected_yield_bps__lte=10000),
                name="ck_food_bom_yield_bps",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class FoodBomComponent(TenantOwnedModel):
    bom = models.ForeignKey(
        FoodBom,
        on_delete=models.CASCADE,
        related_name="components",
        verbose_name="BOM",
    )
    product = models.ForeignKey(
        FoodProduct,
        on_delete=models.PROTECT,
        related_name="bom_usages",
        verbose_name="Insumo",
    )
    quantity_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        verbose_name="Qtd por unidade do acabado",
    )
    scrap_bps = models.PositiveIntegerField(
        default=0,
        verbose_name="Perda planejada (bps)",
        help_text="Extra sobre o consumo. 500 = 5%.",
    )

    class Meta:
        verbose_name = "Componente BOM Food"
        verbose_name_plural = "Componentes BOM Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "bom", "product"],
                name="uq_food_bom_component",
            ),
            models.CheckConstraint(
                condition=Q(quantity_per_unit__gt=0) & Q(scrap_bps__lte=5000),
                name="ck_food_bom_component_qty",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} @ {self.bom_id}"


class FoodCapacitySlot(TenantOwnedModel):
    """Slot de capacidade fabril (dia/horário)."""

    service_date = models.DateField(verbose_name="Data")
    starts_at = models.TimeField(verbose_name="Início")
    ends_at = models.TimeField(verbose_name="Fim")
    name = models.CharField(max_length=128, blank=True, default="", verbose_name="Nome")
    capacity_units = models.PositiveIntegerField(
        default=1, verbose_name="Capacidade (unidades)"
    )
    booked_units = models.PositiveIntegerField(default=0, verbose_name="Reservado")

    class Meta:
        verbose_name = "Slot capacidade Food"
        verbose_name_plural = "Slots capacidade Food"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at"))
                & Q(booked_units__lte=models.F("capacity_units")),
                name="ck_food_capacity_slot",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "service_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.service_date} {self.starts_at}-{self.ends_at}"

    @property
    def free_units(self) -> int:
        return max(0, int(self.capacity_units) - int(self.booked_units))


class FoodProductionOrder(TenantOwnedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planejada"
        IN_PROGRESS = "in_progress", "Em produção"
        DONE = "done", "Concluída"
        CANCELLED = "cancelled", "Cancelada"

    product = models.ForeignKey(
        FoodProduct,
        on_delete=models.PROTECT,
        related_name="production_orders",
        verbose_name="Produto acabado",
    )
    bom = models.ForeignKey(
        FoodBom,
        on_delete=models.PROTECT,
        related_name="production_orders",
        verbose_name="Ficha técnica",
    )
    capacity_slot = models.ForeignKey(
        FoodCapacitySlot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="production_orders",
        verbose_name="Slot",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PLANNED,
        verbose_name="Status",
    )
    quantity_planned = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name="Qtd planejada"
    )
    quantity_produced = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
        verbose_name="Qtd produzida",
    )
    loss_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=0, verbose_name="Perda"
    )
    yield_bps = models.PositiveIntegerField(
        default=10000, verbose_name="Rendimento real (bps)"
    )
    idempotency_key = models.CharField(max_length=128, verbose_name="Idempotência")
    notes = models.TextField(blank=True, default="", verbose_name="Observações")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Início")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Fim")

    class Meta:
        verbose_name = "Ordem de produção Food"
        verbose_name_plural = "Ordens de produção Food"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uq_food_production_order_idem",
            ),
            models.CheckConstraint(
                condition=Q(quantity_planned__gt=0)
                & Q(quantity_produced__gte=0)
                & Q(loss_quantity__gte=0)
                & Q(yield_bps__lte=10000),
                name="ck_food_production_qty",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "product"]),
        ]

    def __str__(self) -> str:
        return f"OP {self.id} ({self.status})"
