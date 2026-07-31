# EXEQ Hub — Smoke Sandbox Inter (D3)

Checklist operacional alinhado a `Docs/Exeq_Hub_Inter_Billing_Integration_Study.md` §9–12 e §15.

## Pré-requisitos

1. Postgres + Redis (se Celery) no ar (`docker compose up -d db redis`).
2. Credenciais Inter sandbox no tenant (`TenantSecret` ou env):
   - `client_id`, `client_secret`, `cert_pem`/`key_pem` (ou paths)
   - Escopos: `boleto-cobranca.read boleto-cobranca.write`
3. `.env`:
   - `PAYMENT_HTTP_MODE=http`
   - `PAYMENT_DEFAULT_PROVIDER=inter`
   - `INTER_API_BASE_URL=https://cdpj-sandbox.partners.uatinter.co`
   - `INTER_WEBHOOK_PUBLIC_URL=https://<host-público>/api/v1/webhooks/gateway`
   - `WEBHOOK_GATEWAY_SECRET=<segredo do Hub>`
4. URL do Hub **HTTPS pública** (ngrok/cloudflared em lab). Inter rejeita localhost.

### Assinatura (gap documentado §9.2)

O Hub exige `X-Webhook-Signature` = HMAC-SHA256 hex do body com `WEBHOOK_GATEWAY_SECRET`.  
O Inter Cobrança **não** usa esse esquema por padrão. Em sandbox/prod:

- **Obrigatório em produção:** proxy que recebe o POST Inter, assina o body e encaminha ao Hub; `WEBHOOK_ALLOWED_IPS` = IP do proxy; segredo ≥32 chars (não o placeholder).
- Lab: allowlist vazia + `DEBUG=true` só para desenvolvimento local.
- Detalhes: `Docs/Exeq_Hub_Inter_Security_Hardening.md`.

## Passos (happy path)

### 1. Auth

```http
POST /api/v1/billing/providers/inter/test-connection
Authorization: Bearer <jwt>
```

Esperado: `{"status":"ok"}`.

### 2. D1 — Cadastrar webhook

```http
PUT /api/v1/billing/providers/inter/webhook
{"webhookUrl":"https://<host>/api/v1/webhooks/gateway"}
```

Ou omitir body e usar `INTER_WEBHOOK_PUBLIC_URL`.

```http
GET /api/v1/billing/providers/inter/webhook
```

Alternativa: `PUT /api/v1/billing/provider` com `{"provider":"inter"}` auto-cadastra se a env estiver setada.

### 3. Emitir cobrança

```http
POST /api/v1/charges/
{
  "idempotency_key": "smoke-1",
  "customer_id": "<uuid>",
  "amount_cents": 500,
  "due_date": "<min_due ISO>",
  "description": "Smoke Inter"
}
```

Esperado: `gateway_ref` (= `codigoSolicitacao`), artefatos (linha/PIX) e `has_boleto_pdf` quando PDF disponível.

### 4. PDF

```http
GET /api/v1/charges/{id}/pdf/
```

Esperado: `application/pdf` (`%PDF`).

### 5. Pagamento simulado (portal sandbox)

Pagar/liquidar no sandbox Inter. Aguardar callback → inbox processada → `Charge.status=paid` + `PaymentEvent`.

Se o callback não chegar:

### 6. D2 — Retry callbacks

```http
POST /api/v1/billing/providers/inter/webhook/callbacks/retry
{
  "codigoSolicitacao": ["<codigoSolicitacao>"],
  "reprocess_local_inbox": true
}
```

- Inter reenvia o POST para o Hub.
- Se já existir inbox `failed` com o mesmo `gateway_ref`, o Hub tenta `reprocess` local.

Inbox avulsa:

```http
POST /api/v1/webhooks/{inbox_id}/reprocess/
```

### 7. Sync manual (rede de segurança)

```http
POST /api/v1/charges/{id}/sync/
```

## Critérios de aceite smoke

- [ ] `test-connection` ok
- [ ] Webhook PUT/GET ok no Inter
- [ ] Charge registrada com `codigoSolicitacao` + linha/PIX (BolePix)
- [ ] PDF baixável (API/Admin/Hub)
- [ ] `RECEBIDO` → `paid` via webhook (ou sync)
- [ ] Retry D2 reprocessa quando necessário
- [ ] Tenant default não chama Asaas no caminho feliz

## Remoção (teardown)

```http
DELETE /api/v1/billing/providers/inter/webhook
```
