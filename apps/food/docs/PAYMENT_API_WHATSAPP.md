# Food — Pagamento via API (contrato WhatsApp)

> Guia completo de entrega, configuração e roteiro QA: [FOOD_PAYMENTS_DELIVERY_QA.md](./FOOD_PAYMENTS_DELIVERY_QA.md)  
> **Roteiro passo a passo Fase A (stub):** [QA_FASE_A_STUB_ROTEIRO.md](./QA_FASE_A_STUB_ROTEIRO.md)

Contrato para integradores emitirem Pix e obterem texto pronto para WhatsApp **sem alterar `apps/channel` na v1**.

## Configuração tenant

```json
{
  "food_payment_provider": "mercadopago",
  "food_payment_methods_enabled": ["pix", "card"]
}
```

Secrets (`TenantSecret`, provider `mercadopago`): `access_token`, `public_key`, `webhook_secret`.

## Fluxo WhatsApp (v1)

1. Cliente monta pedido no bot / integração.
2. `POST /api/v1/food/orders/` com `channel=whatsapp`, `request_payment=true` (ou `request_pix=true`).
3. API cria pedido, emite Pix no gateway Food e devolve `whatsapp_payment` na resposta.
4. Integrador envia `whatsapp_payment.message` no WhatsApp (Meta Cloud API, etc.).
5. Webhook MP confirma pagamento → pedido vai para `paid` / `confirmed`.

Cartão transparente **não** entra no fluxo WhatsApp v1 (checkout Hub ou `payment-intent` com token).

## POST `/api/v1/food/orders/`

### Campos relevantes

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `channel` | string | sim | Use `"whatsapp"` |
| `request_payment` | bool | não | `true` emite pagamento na criação |
| `request_pix` | bool | não | Alias legado; equivalente quando `request_payment` omitido |
| `payment_method` | `"pix"` \| `"card"` | não | Default `pix`. WhatsApp: **somente `pix`** |
| `channel_ref` | string | não | ID externo (ex. message id WhatsApp) |
| `customer_id` | uuid | sim | Cliente com **e-mail** (obrigatório MP) |

### Exemplo

```http
POST /api/v1/food/orders/
Authorization: Bearer <token>
Content-Type: application/json

{
  "customer_id": "…",
  "channel": "whatsapp",
  "channel_ref": "wamid.HBgN…",
  "lines": [{"product_id": "…", "quantity": "1"}],
  "idempotency_key": "wa-order-20250814-001",
  "request_payment": true,
  "payment_method": "pix"
}
```

### Resposta (trecho)

```json
{
  "id": "…",
  "channel": "whatsapp",
  "payment_status": "awaiting_payment",
  "total_cents": 5000,
  "pix_copy_paste": "000201…",
  "whatsapp_payment": {
    "ready": true,
    "message": "Olá Maria!\n\nSeu pedido EXEQ Food foi registrado.\n…",
    "pix_copy_paste": "000201…",
    "order_id": "…",
    "payment_status": "awaiting_payment"
  }
}
```

Para `channel != whatsapp`, `whatsapp_payment` é `null`.

## Helpers Python (Food)

Disponíveis em `apps.food.payments`:

- `build_whatsapp_payment_message(order)` — texto formatado (≤ 4096 chars).
- `build_whatsapp_order_paid_message(order)` — confirmação pós-webhook (uso futuro channel).
- `whatsapp_payment_payload(order)` — dict igual ao campo da API.
- `create_order_with_auto_payment(...)` — pedido + intent em uma chamada de serviço.

## Erros

| Código | Situação |
|--------|----------|
| `food_payment_method_not_allowed` | `payment_method=card` com `channel=whatsapp` |
| `food_payment_email_required` | Cliente sem e-mail (Mercado Pago) |

## Fora de escopo v1

- Envio automático de mensagem em `apps/channel`.
- Cartão via WhatsApp.
- Alterações em `apps/billing`, `apps/hub_v4`, `integrations/payments`.

## Critérios de aceite (EPIC-6)

- **CA-6.1:** Uma chamada `POST` com MP + WhatsApp + `request_payment` retorna Pix copia-e-cola e `whatsapp_payment.message`.
- **CA-6.2:** Pedidos de outros canais não expõem `whatsapp_payment`.
