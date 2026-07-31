# EXEQ Hub — Segurança da integração Inter Cobrança

Complementa `Docs/Exeq_Hub_Inter_Billing_Integration_Study.md` §9.2 e o runbook smoke.

## Modelo de ameaça (resumo)

| Superfície | Risco | Controle Hub |
|------------|-------|----------------|
| `POST /webhooks/gateway` | Forjar `paid` | HMAC `X-Webhook-Signature` + throttle + IP allowlist |
| Segredo fraco / default | Bypass HMAC | Fail-closed em produção (`FORCE_SECURE_SECRETS` / `DEBUG=False`) |
| Callback Inter sem HMAC | Gap do banco | **Proxy assinador** obrigatório (não desligar HMAC) |
| Credenciais Inter | Bleed entre tenants | `TenantSecret` + opcional `ALLOW_ENV_INTER_CREDENTIALS_FALLBACK=false` |
| `webhookUrl` arbitrário | Roubo de callbacks | Em prod só `INTER_WEBHOOK_PUBLIC_URL` |
| Troca de provedor / credenciais | Escalada no tenant | Só `tenant_admin` |
| `GET .../sync` | Side-effect via SAFE | Removido — só `POST` |
| Resolução de tenant | Atribuição errada | Sem `seu_numero` global; `gateway_ref` ambíguo → erro |

## Postura obrigatória em produção

1. `DEBUG=False`
2. `WEBHOOK_GATEWAY_SECRET` aleatório ≥32 chars (nunca o valor de exemplo)
3. `FIELD_ENCRYPTION_KEY` Fernet próprio (rotacionar se usou a chave do repo)
4. Proxy HTTPS: Inter → proxy → Hub, assinando o body com o segredo do Hub
5. `WEBHOOK_ALLOWED_IPS` = IP(s) do proxy (e `WEBHOOK_TRUST_X_FORWARDED_FOR` só atrás de LB confiável)
6. `INTER_WEBHOOK_PUBLIC_URL` = URL canônica do Hub
7. `ALLOW_ENV_INTER_CREDENTIALS_FALLBACK=false` em multi-tenant
8. Credenciais Inter só em `TenantSecret` por tenant

## O que NÃO fazer

- Desligar verificação HMAC “porque o Inter não assina”
- Expor `WEBHOOK_GATEWAY_SECRET` no frontend
- Aceitar `webhookUrl` livre em produção
- Confiar em `X-Forwarded-For` sem proxy confiável

## Checklist de aceite segurança

- [ ] Boot com segredo fraco falha em produção
- [ ] Webhook sem assinatura → 401
- [ ] IP fora da allowlist → 403 (quando configurada)
- [ ] Replay com novo `idempotency_key` não cria 2º `PaymentEvent` na mesma charge
- [ ] Operator não altera provedor/credenciais/webhook
- [ ] Sync só via POST autenticado writer
