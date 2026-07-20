# EXEQ Hub

SaaS multi-tenant (NFS-e, cobrança, DAS) — Modular Monolith Django.

## Documentação oficial

Ordem: Contrato → v1 → v2 → v3.1 → v4 → v5 (em `Docs/`).

## Acordo de engenharia

Código **limpo e enxuto**, com **testes unitários** em toda entrega de regra — válido até o fim do projeto (ver `.cursor/rules/exeq-engineering-agreement.mdc` e `Docs/Exeq_Hub_v2_...`).

## Setup

```bash
docker compose up -d
python -m pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
pytest
```

Opcional (async real): `celery -A config worker -l info`

Postgres Docker: **5433**. Redis: **6379**.

## API

- `POST /api/v1/auth/login` — `{tenant_slug, email, password}`
- `POST /api/v1/auth/refresh`
- `GET/POST/PATCH /api/v1/providers|customers|services`
- `GET/POST /api/v1/fiscal/profiles|catalogs|rules`
- `POST /api/v1/fiscal/catalogs/{id}/publish`
- `POST /api/v1/tax/resolve`
- `POST/GET /api/v1/nf-issue/` — emissão (idempotente)
- `POST /api/v1/nf-issue/{id}/cancel|reprocess`
- `GET/POST /api/v1/charges/` + `POST .../cancel`
- `POST /api/v1/webhooks/gateway` — HMAC (`X-Webhook-Signature`)
- `GET /api/v1/webhooks/` + `POST .../reprocess`
- `GET/POST /api/v1/das/guias/` — DAS/DARF. Default stub (`RECEITA_HTTP_MODE=stub`). HTTP = **SERPRO Integra Contador** (`PGDASD`/`GERARDAS12`), mTLS com A1 primary + `TenantSecret(provider=serpro, key_name=consumer_key|consumer_secret)`. PDF em `StoredFile` (`das_pdf`). DARF exige `SERPRO_ID_SERVICO_GERAR_DARF`. Com `RECEITA_HTTP_MODE=http` (ou `DAS_REQUIRE_ELECTRONIC_PROXY=true`) exige **procuração e-CAC** ativa (`GET/POST /api/v1/electronic-proxies/`).

### Billing / PaymentGateway (multi-provider)

- Providers conhecidos: `asaas` | `inter` | `c6` (porta `PaymentGateway`).
- Seleção: `tenant.settings.payment_provider` → senão `PAYMENT_DEFAULT_PROVIDER` (default `asaas`).
- Stub por padrão (`PAYMENT_HTTP_MODE=stub`). HTTP: **Asaas**, **Inter** e **C6** (`INTER_API_*` / `C6_API_*` + `TenantSecret` `api_token`).
- Spec: `GET /api/v1/openapi.json` ← `Docs/openapi-v4.yaml`.
- Token: `TenantSecret(provider=<kind>, key_name=api_token)`; Asaas também aceita `ASAAS_API_TOKEN`.
- Base Asaas sandbox: `ASAAS_API_BASE_URL=https://sandbox.asaas.com/api/v3`
- **Inter** (Cobrança v3): `POST /cobranca/v3/cobrancas`, `POST .../{codigoSolicitacao}/cancelar`; base sandbox `cdpj-sandbox.partners.uatinter.co` (prod `cdpj.partners.bancointer.com.br`); header opcional `INTER_CONTA_CORRENTE`.
- **C6** (BaaS): `POST /v1/bank_slips`, `PUT /v1/bank_slips/{id}/cancel`; base sandbox `baas-api-sandbox.c6bank.info`; `C6_BILLING_SCHEME=21` (sandbox) / `15` (prod).
- Webhook: HMAC com `WEBHOOK_GATEWAY_SECRET`; payload canônico Hub ou Asaas-like.
- `Charge` só vai para `paid` via `PaymentEvent` ligado ao `WebhookInbox`.

NFS-e: **Focus é o provider default** (`NFSE_DEFAULT_PROVIDER=focus`).  
Layouts: **`nfsen`** (NFS-e Nacional, default / Atibaia) e **`nfse`** (municipal). Betha só via override/`NFSE_BETHA_IBGE_CODES` (legado).  
Simples Nacional com competência ≥ `NFSE_NATIONAL_MANDATORY_FROM` (default `2026-09-01`) **força `nfsen`**.  
Ao autorizar: persiste DANFSe PDF + XML em `NfArtifact` + `StoredFile` (`nf_pdf` / `nf_xml`). Admin: coluna **Baixar** em Artefatos NFS-e; na emissão, inline + ação «Garantir artefatos PDF/XML».

### Focus (token real)

1. Coloque o token no `.env` (`FOCUS_API_TOKEN=...`) **ou** via API autenticada:
   `POST /api/v1/integrations/focus/token` `{"token":"..."}` (gravado criptografado por tenant).
2. Ative HTTP: `FOCUS_HTTP_MODE=http`
3. Base URL homolog: `FOCUS_API_BASE_URL=https://homologacao.focusnfe.com.br`
4. Cadastre a empresa na Focus (habilita NFS-e Nacional homolog):
   `POST /api/v1/integrations/focus/empresas` `{"provider_id":"<uuid>"}`
   Opcional: `webhook_url` ou `FOCUS_WEBHOOK_PUBLIC_URL` + `FOCUS_WEBHOOK_SECRET`.
5. `tenant.focus_layout=nfsen` (default) → `POST /v2/nfsen`. Municipal: `focus_layout=nfse` → `/v2/nfse`.
6. Municípios nacionais: `NFSE_NATIONAL_IBGE_CODES` (default inclui Atibaia `3504107`).
7. Serviços: preencha `codigo_tributacao_nacional_iss` no catálogo (distinto de `lc116_item`).

Webhook Focus (além do poll): `POST /api/v1/webhooks/focus-nfse` com header `X-Focus-Authorization` = `FOCUS_WEBHOOK_SECRET`.

Município Focus (cache): `GET /api/v1/integrations/focus/municipios/{ibge}` → município + JSON exemplo + `suggested_overrides`.

Smoke homolog Atibaia:
```bash
python manage.py smoke_focus_nfsen
python manage.py smoke_focus_nfsen --emit
```

### Admin Django (QA — emissão antecipada)

URL: `/admin/` (superuser ou usuário **Emissor**).

Usuário de emissão (sem superuser):
```bash
python manage.py ensure_emissor_user
```
- Nome: `Emissor`
- E-mail: `emissor@exeq.local`
- Senha padrão: `EmissorNf123!`
- Grupo: `Emissor NFS-e` (cadastros + fiscal + emitir/consultar NFS-e)

Fluxo mínimo para QA testar emissão:
1. Cadastre/ajuste **Tenant**, **Provider**, **Customer**, **Service**, **FiscalProfile** + catálogo/regra publicada (IBGE Atibaia `3504107`).
2. Em **Nf issues** → **Add**: preencha tenant, idempotency_key, prestador, tomador, serviço, perfil fiscal, IBGE, competência, valor (centavos) → Salvar (dispara `create_nf_issue` / Focus stub ou HTTP).
3. Ações em massa: **Consultar status (poll)**, **Cancelar no Focus**, **Reprocessar**.

Site header: `EXEQ Hub — Admin QA`. Channel/WhatsApp UI completa permanece na Sprint 7 plena.

`POST /api/v1/certificates/upload` (multipart: `file`, `cnpj`, `label`, `password`) — validade lida do PFX; PFX criptografado em `.storage/`; senha em `TenantSecret`; torna-se `is_primary` para o CNPJ.

**Gate DAS:** `emitir_guia` exige certificado primary **ativo/expiring** com `key_usage` contendo `das`. Sem certificado → `certificate_not_usable`.

Job: `accounts.scan_expiring_certificates` atualiza status e emite outbox `certificate.expiring` / `certificate.expired`.

### Channel / Evolution

- Stub por padrão (`EVOLUTION_HTTP_MODE=stub`)
- HTTP real: `EVOLUTION_HTTP_MODE=http` + `EVOLUTION_API_BASE_URL` / `EVOLUTION_API_KEY` / `EVOLUTION_INSTANCE`

### Poll Focus

Se a emissão não vier `autorizado`, a nota fica em `polling` e o worker reagenda consulta (`FOCUS_POLL_COUNTDOWN`, default 15s).

### Outbox / notificações

Eventos `nf_issue.authorized`, `charge.paid`, `guia_fiscal.available` são despachados pelo worker (`ops.dispatch_outbox_message`).  
Configure `tenant.settings.notify_phone` (E.164) para enviar WhatsApp via Evolution.

### RLS

Políticas PostgreSQL ativas nas tabelas tenant-scoped (`ops.0003_enable_rls`). Em Docker local o user `exeq` é superuser; o runtime assume o role `exeq_app` (sem `BYPASSRLS`) ao restringir o tenant.
