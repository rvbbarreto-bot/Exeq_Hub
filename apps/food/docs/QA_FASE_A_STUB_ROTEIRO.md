# QA — Fase A (stub) — Roteiro passo a passo

Roteiro manual para validar pagamentos Food **sem credenciais Mercado Pago reais** (`PAYMENT_HTTP_MODE=stub`).

Documento pai: [FOOD_PAYMENTS_DELIVERY_QA.md](./FOOD_PAYMENTS_DELIVERY_QA.md)

---

## 0. Preparação do ambiente (uma vez)

### 0.1 Subir infra e app

**Windows (PowerShell):**

```powershell
cd "C:\Users\riica\OneDrive\Empresas Ricardo\Exeq\Exeq_Hub"
.\bootstrap.ps1 -Bg
```

**Linux/macOS:**

```bash
./bootstrap.sh --bg
```

**Manual equivalente:**

```powershell
docker compose up -d
copy .env.example .env   # se ainda não existir
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Confirme que responde: [http://localhost:8000/hub/login/](http://localhost:8000/hub/login/)

### 0.2 Variáveis `.env` para Fase A

Edite `.env` na raiz do projeto:

```env
PAYMENT_HTTP_MODE=stub
FOOD_MP_WEBHOOK_SECRET=mp-webhook-test-secret
DJANGO_DEBUG=true
```

Reinicie o `runserver` após alterar o `.env`.

### 0.3 Criar tenant, usuário e dados de teste

**Comando (recomendado — idempotente):**

```powershell
python manage.py food_onboard_qa --mp-webhook-secret mp-webhook-test-secret
```

Verificar prontidão:

```powershell
python manage.py food_mp_check --tenant food-qa --strict
```

**Alternativa — shell Django** (equivalente ao comando acima):

Abra um terminal e rode:

```powershell
python manage.py shell
```

Cole o bloco abaixo (cria tenant **food-qa**, usuário QA e catálogo mínimo):

```python
from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.food.services import create_food_customer, create_food_product

roles = {r.code: r for r in ensure_system_roles()}

tenant, _ = Tenant.objects.get_or_create(
    slug="food-qa",
    defaults={
        "legal_name": "Food QA LTDA",
        "document": "11222333000181",
        "settings": {
            "food_payment_provider": "mercadopago",
            "food_payment_methods_enabled": ["pix", "card"],
            "payment_provider": "inter",
        },
    },
)
# Garante settings MP mesmo se tenant já existia
tenant.settings = {
    **(tenant.settings or {}),
    "food_payment_provider": "mercadopago",
    "food_payment_methods_enabled": ["pix", "card"],
    "payment_provider": "inter",
}
tenant.save(update_fields=["settings"])

user, created = User.objects.get_or_create(
    email="qa.food@exeq.local",
    defaults={"name": "QA Food", "is_active": True},
)
if created:
    user.set_password("Secret123!")
    user.save()

TenantMembership.objects.get_or_create(
    tenant=tenant,
    user=user,
    defaults={"role": roles["tenant_admin"], "is_active": True},
)

customer_com_email = create_food_customer(
    tenant=tenant,
    name="Maria QA",
    phone_e164="+5511988880001",
    document="52998224725",
    email="maria.qa@example.com",
)
customer_sem_email = create_food_customer(
    tenant=tenant,
    name="João Sem Email",
    phone_e164="+5511988880002",
    document="39053344705",
    email="",
)
product = create_food_product(
    tenant=tenant,
    sku="QA-FOOD-01",
    name="Produto QA Food",
    price_cents=5000,
    cost_cents=2000,
    initial_stock=10,
)

print("OK — tenant:", tenant.slug)
print("Login Hub/API:", user.email, "/ Secret123!")
print("customer_id (com email):", customer_com_email.id)
print("customer_id (sem email):", customer_sem_email.id)
print("product_id:", product.id)
```

**Anote os UUIDs** impressos — serão usados nos cenários abaixo.

---

## 1. Links e acessos

| Recurso | URL |
|---------|-----|
| **Hub — login** | [http://localhost:8000/hub/login/](http://localhost:8000/hub/login/) |
| **Hub — pedidos Food** | [http://localhost:8000/hub/food/pedidos/](http://localhost:8000/hub/food/pedidos/) |
| **Hub — novo pedido** | [http://localhost:8000/hub/food/pedidos/novo/](http://localhost:8000/hub/food/pedidos/novo/) |
| **Admin Django** | [http://localhost:8000/admin/](http://localhost:8000/admin/) |
| **OpenAPI (referência)** | [http://localhost:8000/api/v1/openapi.json](http://localhost:8000/api/v1/openapi.json) |
| **API — login** | `POST` [http://localhost:8000/api/v1/auth/login](http://localhost:8000/api/v1/auth/login) |
| **API — pedidos Food** | [http://localhost:8000/api/v1/food/orders/](http://localhost:8000/api/v1/food/orders/) |
| **Webhook MP Food** | `POST` [http://localhost:8000/api/v1/food/webhooks/mercadopago](http://localhost:8000/api/v1/food/webhooks/mercadopago) |

### Credenciais lab (criadas no passo 0.3)

| Campo | Valor |
|-------|-------|
| Tenant slug | `food-qa` |
| E-mail | `qa.food@exeq.local` |
| Senha | `Secret123!` |
| Papel | `tenant_admin` |

### Obter token API (reutilize em todos os cenários API)

**PowerShell:**

```powershell
$body = @{
  tenant_slug = "food-qa"
  email       = "qa.food@exeq.local"
  password    = "Secret123!"
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method POST -ContentType "application/json" -Body $body

$TOKEN = $login.access
Write-Host "Token:" $TOKEN
```

**curl (Git Bash / WSL):**

```bash
export TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug":"food-qa","email":"qa.food@exeq.local","password":"Secret123!"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access'])")
echo $TOKEN
```

Substitua `$CUSTOMER_ID`, `$PRODUCT_ID` etc. pelos UUIDs anotados no passo 0.3.

---

## 2. Cenários — passo a passo

Marque **Pass / Fail** e guarde evidência (screenshot ou JSON).

---

### A1 — Migration aplicada

| | |
|---|---|
| **Objetivo** | Confirmar tabela `FoodPayment` no banco |
| **Pré-condição** | Docker Postgres up |

**Passos:**

1. No terminal: `python manage.py showmigrations food`
2. Localize a linha `[X] 0006_food_payment_foundation`

**Resultado esperado:** migration `0006` marcada como aplicada.

**Evidência sugerida:** print do terminal.

---

### A2 — Router default Inter (legado)

| | |
|---|---|
| **Objetivo** | Tenant sem `food_payment_provider` usa Inter via billing |
| **ID cenário** | A2 |

**Passos:**

1. Shell Django:

```python
from apps.accounts.models import Tenant
t = Tenant.objects.get(slug="food-qa")
s = dict(t.settings or {})
s.pop("food_payment_provider", None)
t.settings = s
t.save(update_fields=["settings"])
```

2. Crie pedido counter via API:

```powershell
$order = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/food/orders/" `
  -Method POST -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -Body (@{
    customer_id = "$CUSTOMER_ID"
    channel = "counter"
    lines = @(@{ product_id = "$PRODUCT_ID"; quantity = "1" })
    idempotency_key = "qa-a2-inter-001"
    request_pix = $true
  } | ConvertTo-Json -Depth 5)
$order | ConvertTo-Json -Depth 5
```

3. Abra no Hub: [http://localhost:8000/hub/food/pedidos/](http://localhost:8000/hub/food/pedidos/) → clique **Ver** no pedido.

**Resultado esperado:**

- Resposta API contém `charge_id` preenchido (UUID)
- Campo `payment` pode ser `null` (Inter usa `billing.Charge`)
- Hub mostra referência de cobrança billing

**Restaurar MP para cenários seguintes:**

```python
from apps.accounts.models import Tenant
t = Tenant.objects.get(slug="food-qa")
t.settings = {**(t.settings or {}), "food_payment_provider": "mercadopago"}
t.save(update_fields=["settings"])
```

---

### A3 — Router Mercado Pago stub (sem billing)

| | |
|---|---|
| **Objetivo** | MP cria `FoodPayment`, não chama billing |
| **ID cenário** | A3 |

**Passos:**

1. Confirme `food_payment_provider=mercadopago` no tenant (passo de restauração acima).
2. API — criar pedido **sem** pagamento ainda:

```powershell
$order = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/food/orders/" `
  -Method POST -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -Body (@{
    customer_id = "$CUSTOMER_ID"
    channel = "counter"
    lines = @(@{ product_id = "$PRODUCT_ID"; quantity = "1" })
    idempotency_key = "qa-a3-mp-001"
  } | ConvertTo-Json -Depth 5)
$ORDER_ID = $order.id
```

3. Emitir Pix:

```powershell
$pix = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/food/orders/$ORDER_ID/pix/" `
  -Method POST -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $TOKEN" } -Body "{}"
$pix | ConvertTo-Json -Depth 5
```

**Resultado esperado:**

- `charge_id` = `null`
- `payment.provider` = `"mercadopago"`
- `payment.method` = `"pix"`
- Admin → Food → Pagamentos Food: registro novo (opcional)

Link Hub pedido: `http://localhost:8000/hub/food/pedidos/<ORDER_ID>/`

---

### A4 — Pix stub MP (copia e cola)

| | |
|---|---|
| **Objetivo** | Stub retorna Pix EMV válido |
| **ID cenário** | A4 |
| **Depende de** | A3 (mesmo pedido) |

**Passos:**

1. No JSON do passo A3, verifique `pix_copy_paste`.
2. Abra o pedido no Hub: [http://localhost:8000/hub/food/pedidos/{ORDER_ID}/](http://localhost:8000/hub/food/pedidos/)

**Resultado esperado:**

- `pix_copy_paste` começa com `000201`
- Hub exibe bloco **PIX copia e cola** + botão **Copiar Pix**
- Provedor exibido: **Mercado Pago**

---

### A5 — Idempotência Pix

| | |
|---|---|
| **Objetivo** | Segunda chamada não duplica pagamento |
| **ID cenário** | A5 |

**Passos:**

1. Repita `POST .../orders/{ORDER_ID}/pix/` (mesmo `$ORDER_ID` do A3).
2. Compare `payment.id` nas duas respostas.

**Resultado esperado:**

- HTTP `200` nas duas chamadas
- Mesmo `payment.id`
- Admin: apenas **1** `FoodPayment` para o pedido

---

### A6 — E-mail obrigatório (Mercado Pago)

| | |
|---|---|
| **Objetivo** | Cliente sem e-mail bloqueia emissão MP |
| **ID cenário** | A6 |

**Passos:**

1. Crie pedido com cliente **sem e-mail** (`customer_id` do João):

```powershell
$order = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/food/orders/" `
  -Method POST -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -Body (@{
    customer_id = "$CUSTOMER_SEM_EMAIL_ID"
    channel = "counter"
    lines = @(@{ product_id = "$PRODUCT_ID"; quantity = "1" })
    idempotency_key = "qa-a6-no-email"
  } | ConvertTo-Json -Depth 5)

try {
  Invoke-RestMethod -Uri "http://localhost:8000/api/v1/food/orders/$($order.id)/pix/" `
    -Method POST -ContentType "application/json" `
    -Headers @{ Authorization = "Bearer $TOKEN" } -Body "{}"
} catch {
  $_.ErrorDetails.Message
}
```

2. Abra o pedido no Hub.

**Resultado esperado:**

- API retorna HTTP **422**
- JSON contém `"code": "food_payment_email_required"`
- Hub mostra aviso de e-mail obrigatório e **não** exibe botão **Gerar pagamento Pix**

---

### A7 — WhatsApp CA-6.1 (pedido + pagamento + mensagem)

| | |
|---|---|
| **Objetivo** | Uma chamada retorna Pix + `whatsapp_payment.message` |
| **ID cenário** | A7 |

**Passos:**

1. API — criar pedido WhatsApp com pagamento automático:

```powershell
$wa = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/food/orders/" `
  -Method POST -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -Body (@{
    customer_id = "$CUSTOMER_ID"
    channel = "whatsapp"
    channel_ref = "wamid.qa-a7-001"
    lines = @(@{ product_id = "$PRODUCT_ID"; quantity = "1" })
    idempotency_key = "qa-a7-wa-001"
    request_payment = $true
    payment_method = "pix"
  } | ConvertTo-Json -Depth 5)
$wa | ConvertTo-Json -Depth 6
```

**Resultado esperado:**

- `channel` = `"whatsapp"`
- `channel_ref` = `"wamid.qa-a7-001"`
- `pix_copy_paste` preenchido (`000201...`)
- `whatsapp_payment.ready` = `true`
- `whatsapp_payment.message` contém:
  - nome **Maria QA**
  - texto **Pix Copia e Cola**
  - valor **R$ 50,00** (5000 centavos)
- `len(whatsapp_payment.message)` ≤ 4096

**Evidência:** salvar JSON completo da resposta.

---

### A8 — WhatsApp CA-6.2 (outros canais)

| | |
|---|---|
| **Objetivo** | Canal ≠ whatsapp não expõe bloco WhatsApp |
| **ID cenário** | A8 |

**Passos:**

1. Crie pedido `counter` com `request_payment=true` (igual A7, mudando `channel`).
2. Observe campo `whatsapp_payment` na resposta.

**Resultado esperado:** `"whatsapp_payment": null`

---

### A9 — WhatsApp rejeita cartão

| | |
|---|---|
| **Objetivo** | Validação de produto v1 |
| **ID cenário** | A9 |

**Passos:**

```powershell
try {
  Invoke-RestMethod -Uri "http://localhost:8000/api/v1/food/orders/" `
    -Method POST -ContentType "application/json" `
    -Headers @{ Authorization = "Bearer $TOKEN" } `
    -Body (@{
      customer_id = "$CUSTOMER_ID"
      channel = "whatsapp"
      lines = @(@{ product_id = "$PRODUCT_ID"; quantity = "1" })
      idempotency_key = "qa-a9-wa-card"
      request_payment = $true
      payment_method = "card"
    } | ConvertTo-Json -Depth 5)
} catch {
  $_.ErrorDetails.Message
}
```

**Resultado esperado:**

- HTTP **400**
- Erro em `payment_method` / code `food_payment_method_not_allowed`

---

### A10 — Hub painel Mercado Pago

| | |
|---|---|
| **Objetivo** | UI Hub exibe painel de pagamento MP |
| **ID cenário** | A10 |

**Passos:**

1. Login Hub: [http://localhost:8000/hub/login/](http://localhost:8000/hub/login/)
   - Tenant: `food-qa`
   - E-mail: `qa.food@exeq.local`
   - Senha: `Secret123!`
2. Menu **Food → Pedidos**: [http://localhost:8000/hub/food/pedidos/](http://localhost:8000/hub/food/pedidos/)
3. Abra o pedido do cenário **A7** (WhatsApp com Pix).

**Resultado esperado:**

- Seção **Pagamento** visível
- Provedor: **Mercado Pago**
- Pix copia e cola preenchido
- Botão **Copiar Pix** funciona (cola na área de transferência ou prompt)

**Evidência:** screenshot da tela do pedido.

---

### A11 — Hub cartão stub

| | |
|---|---|
| **Objetivo** | Checkout cartão em modo lab aprova pedido |
| **ID cenário** | A11 |

**Passos:**

1. Crie pedido counter sem pagamento (API, idempotency `qa-a11-card`).
2. Login Hub → abra o pedido: `http://localhost:8000/hub/food/pedidos/<ORDER_ID>/`
3. Role até **Cartão de crédito**.
4. Confirme texto: *Modo lab (stub): dados de cartão não são enviados ao servidor.*
5. Clique **Pagar com cartão** (stub não pede número de cartão).

**Resultado esperado:**

- Mensagem verde: pagamento aprovado (ou status pago na tela)
- `payment_status` = **Pago**
- Status pedido = **Confirmado**

Alternativa via API:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/food/orders/$ORDER_ID/payment-intent/" `
  -Method POST -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -Body '{"method":"card","token":"stub_card_token","payment_method_id":"visa","installments":1}'
```

---

### A12 — Webhook assinatura inválida

| | |
|---|---|
| **Objetivo** | Segurança do endpoint público |
| **ID cenário** | A12 |

**Passos:**

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/food/webhooks/mercadopago" `
  -Method POST -ContentType "application/json" `
  -Body '{"type":"payment","data":{"id":"999"}}' `
  -SkipHttpErrorCheck | Select-Object StatusCode, Content
```

**Resultado esperado:** HTTP **401** (assinatura inválida ou ausente)

---

### A13 — Webhook aprovado (confirma pedido + estoque)

| | |
|---|---|
| **Objetivo** | Fluxo completo Pix pendente → webhook → pago |
| **ID cenário** | A13 |

**Passos:**

1. Anote estoque atual do produto QA (Hub ou Admin).
2. Crie pedido WhatsApp + Pix (repita A7 com idempotency `qa-a13-webhook`).
3. Anote `payment.provider_payment_id` da resposta (ex. `mp_stub_abc123...`).
4. No terminal, simule webhook assinado:

```powershell
python manage.py shell
```

```python
import json, uuid
from decimal import Decimal
from django.test import Client
from django.conf import settings

settings.FOOD_MP_WEBHOOK_SECRET = "mp-webhook-test-secret"

from apps.food.models import FoodOrder, FoodPayment
from apps.food.webhook_views import sign_mercadopago_webhook_test

ORDER_ID = "COLE-UUID-DO-PEDIDO-A13"
order = FoodOrder.objects.get(pk=ORDER_ID)
payment = FoodPayment.objects.filter(order=order).latest("created_at")
payment_id = payment.provider_payment_id

payload = {
    "action": "payment.updated",
    "type": "payment",
    "data": {"id": payment_id},
    "id": 999001,
}
body = json.dumps(payload).encode()
request_id = str(uuid.uuid4())
signature = sign_mercadopago_webhook_test(
    secret=settings.FOOD_MP_WEBHOOK_SECRET,
    data_id=str(payment_id),
    request_id=request_id,
)

client = Client()
response = client.post(
    "/api/v1/food/webhooks/mercadopago",
    data=body,
    content_type="application/json",
    HTTP_X_SIGNATURE=signature,
    HTTP_X_REQUEST_ID=request_id,
)
print("HTTP", response.status_code, response.content.decode())
order.refresh_from_db()
payment.refresh_from_db()
print("order.payment_status", order.payment_status)
print("order.status", order.status)
print("payment.status", payment.status)
```

5. Recarregue o pedido no Hub.

**Resultado esperado:**

- Webhook HTTP **200**
- `order.payment_status` = `paid`
- `order.status` = `confirmed`
- Estoque do produto reduziu em 1 (de 10 → 9 se só este cenário consumiu)

**Teste extra (dedupe):** execute o mesmo bloco webhook **duas vezes** com o mesmo `request_id` — estoque não deve baixar de novo.

---

## 3. Checklist resumo Fase A

| ID | Cenário | Pass | Fail | Observações |
|----|---------|:----:|:----:|-------------|
| A1 | Migration 0006 | ☐ | ☐ | |
| A2 | Router Inter default | ☐ | ☐ | |
| A3 | Router MP sem billing | ☐ | ☐ | |
| A4 | Pix copia e cola stub | ☐ | ☐ | |
| A5 | Idempotência Pix | ☐ | ☐ | |
| A6 | E-mail obrigatório MP | ☐ | ☐ | |
| A7 | WhatsApp CA-6.1 | ☐ | ☐ | |
| A8 | WhatsApp CA-6.2 | ☐ | ☐ | |
| A9 | WhatsApp rejeita cartão | ☐ | ☐ | |
| A10 | Hub painel MP | ☐ | ☐ | |
| A11 | Hub cartão stub | ☐ | ☐ | |
| A12 | Webhook 401 | ☐ | ☐ | |
| A13 | Webhook pago + estoque | ☐ | ☐ | |

---

## 4. Regressão automatizada (opcional)

Após Fase A manual, rode:

```powershell
python -m pytest apps/food/tests/test_payment_router.py `
  apps/food/tests/test_mp_pix.py `
  apps/food/tests/test_mp_webhook.py `
  apps/food/tests/test_mp_webhook_security.py `
  apps/food/tests/test_mp_card.py `
  apps/food/tests/test_hub_payment_ui.py `
  apps/food/tests/test_whatsapp_payment_contract.py -q
```

---

## 5. Problemas comuns

| Problema | Solução |
|----------|---------|
| `connection timeout` no pytest | `docker compose up -d db` |
| Login Hub falha | Confirmar tenant slug `food-qa` e usuário do passo 0.3 |
| Token API 401 | Refazer login; token expira |
| Webhook 401 no A13 | Conferir `FOOD_MP_WEBHOOK_SECRET=mp-webhook-test-secret` no `.env` |
| Hub sem botão cartão | Tenant precisa `food_payment_methods_enabled` com `"card"` |
| `charge_id` null no A2 | Normal para MP; no A2 (Inter) deve aparecer |

---

**Versão:** 2026-08-14 · Fase A stub · commit `95e0282`
