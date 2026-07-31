# EXEQ Hub — Estudo de Integração Spedy (NFS-e)

| Campo | Valor |
|-------|--------|
| Status | **0.1.0** — estudo / plano (sem implementação) |
| Data | 2026-07-29 |
| Fontes oficiais | [docs.spedy.com.br](https://docs.spedy.com.br/) (Redoc) · OpenAPI [`https://api.spedy.com.br/swagger/v1/swagger.json`](https://api.spedy.com.br/swagger/v1/swagger.json) · [`llms.txt`](https://api.spedy.com.br/llms.txt) · municípios [`app.spedy.com.br/integrated-cities`](https://app.spedy.com.br/integrated-cities) |
| Escopo | Avaliar Spedy como **novo adapter** atrás da porta `NfseProvider` (junto a Focus/Betha) |
| Não fazer nesta entrega | Implementar adapter, alterar Focus, mudar regras fiscais |

> **Nota metodológica:** a UI em `docs.spedy.com.br` é SPA (Redoc). O conteúdo normativo foi extraído do **Swagger OpenAPI 3.0.1** e da descrição embutida (inclui “Ambiente de testes”, autenticação, fluxo assíncrono, webhooks, Reforma 2026). Onde a doc pública é ambígua, marca-se **a confirmar em sandbox**.

> **Atenção:** `docs.spedy.ai` (PATs `spedy_pat_…`, tickets) **não** é a API fiscal brasileira. Este estudo usa apenas `api.spedy.com.br` / `sandbox-api.spedy.com.br`.

---

## 0. Contrato atual do Hub (`NfseProvider`) — resumo

Porta: `integrations/nfse/port.py`.

- **`NfseProvider` (Protocol):** `kind: str` + `emitir(payload)` + `consultar(ref)` + `cancelar(ref, justificativa, codigo_cancelamento?)` → `NfseEmitResult(external_ref, status, raw)`.
- **Adapters hoje:** `FocusNfseProvider` (default), `BethaNfseProvider` (legado SOAP via allowlist IBGE).
- **Roteamento:** `resolve_emission_route` / `get_nfse_provider` (`factory.py` + `router.py`):
  - default `NFSE_DEFAULT_PROVIDER=focus`;
  - layouts Focus `nfsen` (nacional) vs `nfse` (municipal);
  - overrides por `tenant.settings.nfse_provider_by_ibge` / `nfse_layout_by_ibge`;
  - Simples + competência ≥ `NFSE_NATIONAL_MANDATORY_FROM` força `focus`+`nfsen`.
- **Auth Focus:** Basic Auth (`token`, senha vazia); token global `FOCUS_API_TOKEN` ou `TenantSecret(provider=focus, key_name=api_token)`.
- **Emissão:** `process_queued_issue` monta body via `build_focus_body` / mappers → `provider.emitir` → grava `focus_ref` + `focus_status_raw` → `POLLING` ou `AUTHORIZED`.
- **Polling:** Celery `poll_nf_issue_task` com `FOCUS_POLL_COUNTDOWN` (default 15s) + webhook Focus.
- **Cancelamento:** `DELETE` Focus + justificativa 15–255 chars (regra Hub).
- **Artefatos:** após `AUTHORIZED`, `ensure_authorized_artifacts` persiste PDF/XML em `NfArtifact` + `StoredFile` (baixa URLs do raw Focus ou stub).
- **Webhook:** `POST /api/v1/webhooks/focus-nfse` com header `X-Focus-Authorization` = `FOCUS_WEBHOOK_SECRET`.
- **Self-service empresa:** `FocusEmpresaClient` (`POST/PUT /v2/empresas`) + hook Focus; certificado A1 no Hub (`DigitalCertificate`) é domínio próprio (SERPRO/DAS etc.) — Focus NFS-e nacional costuma operar com cadastro empresa + token, não upload A1 no mesmo fluxo do Hub.
- **Campos fiscais relevantes:** `codigo_tributacao_nacional_iss`, `lc116_item`/`service_code`, IBGE, regime, RTC (`codigo_nbs`, IBS/CBS via `RTC_NFSEN_MODE` / `focus_fields`).

**Implicação:** Spedy deve entrar como `kind="spedy"` na mesma porta, com mapper próprio e resolução de rota (tenant/IBGE), **sem** fork do InvoiceEngine.

---

## 1. Achados Spedy (Fase 1)

### 1.1 Autenticação

| Item | Documentado |
|------|-------------|
| Mecanismo | Header **`X-Api-Key`** (security scheme `ApiKey` no OpenAPI) |
| OAuth2 / Bearer PAT | **Não** na API fiscal `api.spedy.com.br` |
| Origem da chave | Retornada **uma vez** em `POST /v1/companies` → `result.apiCredentials.apiKey`; depois ofuscada no GET |
| Regeneração | Backoffice: Perfil → Minha empresa → Credenciais da API → “Gerar nova chave” (revoga a anterior) |
| Escopo | **Uma API Key por empresa**. Empresa **principal** (primeira da conta): gerencia empresas + NF. Demais: só operações de NF |
| Sandbox vs produção | Contas **separadas** (Plano Desenvolvedor no sandbox). Chaves **distintas** por ambiente |

### 1.2 Ambientes

| Ambiente | API | Backoffice |
|----------|-----|------------|
| Produção | `https://api.spedy.com.br/v1` | (app produção) |
| Testes | `https://sandbox-api.spedy.com.br/v1` | `https://sandbox-app.spedy.com.br` |

Mesma lógica de API; isolamento total (nova conta no sandbox). Docs: “mesmo endpoint, mesma lógica, sem custo real” no material comercial; tecnicamente URLs e conta distintas.

### 1.3 Cadastro de empresa / tenant fiscal

**Há API self-service** (diferente de “só painel”):

| Operação | Endpoint |
|----------|----------|
| Criar / listar / obter / alterar / excluir | `POST/GET/PUT/DELETE /v1/companies` |
| Campos mínimos create | `name`, `legalName`, `federalTaxNumber` (CNPJ), `address` |
| IM / IE | `cityTaxNumber`, `stateTaxNumber` |
| Config NFS-e (série, ambiente, `issueType`, credenciais prefeitura…) | `GET/PUT /v1/companies/{id}/settings` (`serviceInvoice`) |
| Nacional | `issueType = "annfs"` (Ambiente Nacional NFS-e) |

Isso **preserva** o padrão self-service do Hub (análogo a `FocusEmpresaClient`), desde que o Hub use a API Key da **empresa principal** da conta Spedy para provisionar CNPJs dos tenants/prestadores.

### 1.4 Certificado digital

| Item | Documentado |
|------|-------------|
| Upload via API | **Sim:** `POST /v1/companies/{id}/certificates` multipart (`certificateFile` `.pfx` + `password`) |
| Consulta | `GET /v1/companies/{id}/certificates` → validade, subject, `isActive` |
| Manual only? | Não é exclusivo do painel — API cobre upload |
| Exigência por município | `GET /v1/service-invoices/cities` → `provider.options.requiresDigitalCertificate` |

**Gap vs Hub:** hoje o Hub já armazena A1 (`DigitalCertificate` + secret). Para Spedy, o fluxo natural é **reenviar o PFX** para a Spedy (ou exigir upload no onboarding) — a assinatura fiscal fica no lado Spedy. **A confirmar em sandbox:** se certificado no Hub pode ser reutilizado byte-a-byte sem reupload periódico, e se há webhook de expiração (blog menciona; **não** listado nos eventos oficiais do OpenAPI abaixo).

### 1.5 Emissão NFS-e

Duas formas:

1. **`POST /v1/orders`** — venda simples; Spedy resolve tributação pela config da empresa (pouco controle — ruim para TaxEngine do Hub).
2. **`POST /v1/service-invoices`** — **nota completa** (recomendado para o Hub).

Fluxo **assíncrono:** resposta imediata com `status: enqueued` → fila interna → prefeitura/SEFIN → `authorized` / `rejected` / etc. Recomendam **webhook**; polling via `GET /v1/service-invoices/{id}` (não bate na prefeitura). `POST .../check-status` reconcilia com a prefeitura.

Campos relevantes do `CreateServiceInvoiceDto` (required: `description`, `total`):

| Spedy | Uso |
|-------|-----|
| `integrationId` (≤36) | Id do cliente + **idempotência** |
| `effectiveDate` | Competência |
| `issuedOn` | Emissão |
| `receiver` | Tomador |
| `federalServiceCode` | LC 116 |
| `nationalTaxationCode` | Código tributação nacional |
| `cityServiceCode` | Código municipal |
| `nbsCode` | NBS |
| `cstPisCofins` | Nacional |
| `taxationType` | Exigibilidade ISS |
| `total.invoiceAmount` (+ ISS rates/amounts…) | Valores |
| `location` / `taxLocation` | Município prestação / incidência (IBGE `city.code`) |
| `ibsCbs` | CST / classification / operationIndicatorCode / isPersonalUse |
| `national` | Benefício municipal, construção, evento |

Reforma 2026: docs pedem `issueType=annfs`, NBS, CST PIS/COFINS, bloco `ibsCbs`; IBS/CBS cálculo automático (0,1% / 0,9% na transição) se habilitado nas configs gerais. ISS/PIS/COFINS **continuam obrigatórios** na transição.

### 1.6 Idempotência

Campo **`integrationId`** (máx. 36 caracteres):

- associa nota ao ID do sistema cliente;
- segundo `POST` com mesmo `integrationId` **atualiza** em vez de criar (retries/timeouts);
- rejeitada: reenviar POST corrigido com o **mesmo** `integrationId`.

**Mapeamento Hub:** `NfIssue.id` (UUID=36) ou hash curto de `idempotency_key` (UUID do model já cabe). **Não** confundir com `idempotency_key` interno do Hub (único por tenant) — usar o UUID da emissão como `integrationId` é o caminho mais limpo.

### 1.7 Status / polling

`InvoiceStatus`: `created` | `enqueued` | `received` | `authorized` | `inContingent` | `rejected` | `canceled` | `denied` | `removed` | `disabled`.

`processingDetail.status`: `processing` | `success` | `failed` — **`success` ≠ autorizado** (rejeitada também pode ter processing success).

Mapeamento sugerido → FSM Hub:

| Spedy | Hub |
|-------|-----|
| `enqueued` / `received` / `created` | `polling` (após submit) |
| `authorized` | `authorized` |
| `rejected` / `denied` | `rejected` |
| `canceled` | `cancelled` |
| `inContingent` | **NFS-e:** docs dizem contingência é NF-e/NFC-e; para NFS-e tratar como **a confirmar** (provavelmente raro) |

Polling Hub atual (`FOCUS_POLL_COUNTDOWN`) continua útil como **fallback**; estratégia preferida Spedy = webhook.

### 1.8 Cancelamento

- `DELETE /v1/service-invoices/{id}` body `{ "reason": "..." }` (required).
- **Prazo / regras municipais:** **não documentados** de forma geral no OpenAPI → **a confirmar em sandbox** e por município (`cities`).
- Hub já exige justificativa 15–255 — alinhar `reason` a essa regra (ou validar limites Spedy no sandbox).

### 1.9 Artefatos

- `GET /v1/service-invoices/{id}/pdf`
- `GET /v1/service-invoices/{id}/xml`

Não vêm embutidos no POST inicial; webhook de autorização traz o objeto nota (como GET), mas PDF/XML são endpoints dedicados. Hub deve adaptar `ensure_authorized_artifacts` para baixar com `X-Api-Key` quando `provider.kind == spedy`.

### 1.10 Webhooks

| Item | Documentado |
|------|-------------|
| Config | `POST /v1/webhooks` — **por conta**, não por empresa |
| Eventos | `invoice.status_changed`, `invoice.authorized`, `invoice.rejected`, `invoice.canceled` (+ `invoice.contingency` na narrativa de contingência NFC-e) |
| Payload | `{ id, event, data }` onde `data` ≈ GET da nota |
| Retry entrega | 5 tentativas: 5m → 30m → 1h → 4h → 16h; depois **desabilita** webhook |
| Assinatura HMAC / header secreto | **Não documentado** no OpenAPI / intro oficial (0 ocorrências de hmac/signature/secret) |

**Risco alto:** validação de autenticidade no Hub precisará de estratégia alternativa **a confirmar com Spedy** (IP allowlist, secret em query, mTLS, etc.). Até lá, não tratar webhook como source of trust sem mitigação.

### 1.11 Erros e retries (lado Spedy)

- Emissão: fila interna + retry exponencial **no lado Spedy** (async) — Hub **não** deve re-emitir agressivamente no mesmo `integrationId` sem correção de payload.
- HTTP **429** rate limit; headers `x-rate-limit-*`.
- Rejeições: `processingDetail.code` com prefixo `SPD` = validação Spedy; senão código da autoridade.
- Hub: manter FSM + poll/webhook; retries de rede no client HTTP com cuidado por causa da idempotência por `integrationId`.

### 1.12 Rate limits e multi-CNPJ

| Limite | Valor |
|--------|-------|
| RPM | 60 / minuto |
| Burst | máx. 5 / segundo |
| HTTP | 429 + `x-rate-limit-reset` |

**Multi-CNPJ:** conta Spedy com empresa principal + N empresas (CNPJs). Cada empresa tem API Key. Modelo Hub sugerido:

1. Credencial **plataforma** (empresa principal) em env / secret global → CRUD companies + certificates + settings + webhooks.
2. Por tenant/prestador: gravar `TenantSecret(provider=spedy, key_name=api_key)` + `spedy_company_id`.
3. Emissão com a API Key **da empresa emissora** (não a da principal), salvo se a doc sandbox provar que a principal opera em nome das filhas (**a confirmar** — texto oficial diz “demais empresas: apenas NF”, não que a principal emite por elas).

Blog comercial fala em “um token + CNPJ no payload”; **OpenAPI oficial contradiz** (key por empresa, sem campo CNPJ emissor no `CreateServiceInvoiceDto`). **Seguir OpenAPI**; validar mito do blog no sandbox.

### 1.13 Municípios / nacional vs municipal

- Lista: `GET /v1/service-invoices/cities` + UI integrated-cities.
- Flags: `useNationalLayout`, `supportsTaxReform`, `nationalServiceInvoiceRegimes` (`none|all|mei|simplesNacional|regimeNormal`), opções RPS/série/lote/certificado/NBS/LC116.
- Nacional: configurar `issueType=annfs` nas settings da empresa.
- Cobertura: **não** é “todo município do Brasil automaticamente” — só integrados. Comparar com Hub: Focus `nfsen` Atibaia/allowlist + Betha legado.

**A confirmar:** Atibaia (`3504107`) e demais IBGEs do Hub estão na lista Spedy sandbox/prod.

---

## 2. Tabela comparativa Focus vs Spedy

| Dimensão | Focus (Hub hoje) | Spedy |
|----------|------------------|-------|
| Auth | Basic (token) | `X-Api-Key` por empresa |
| Ambientes | `homologacao.focusnfe.com.br` vs prod | `sandbox-api` vs `api` (contas separadas) |
| Cadastro empresa | `POST/PUT /v2/empresas` (API) | `POST/PUT /v1/companies` + `/settings` (API) |
| Certificado A1 | Fora do fluxo NFS-e Focus no Hub | Upload `.pfx` via API |
| Payload emissão | `/v2/nfsen` plano ou `/v2/nfse` aninhado | `POST /v1/service-invoices` (DTO rico) |
| Idempotência | `ref` query Focus + `idempotency_key` Hub | `integrationId` (≤36) |
| Status inicial | sync stub / async poll | sempre async `enqueued` |
| Polling | `GET /v2/nfsen\|nfse/{ref}` | `GET /v1/service-invoices/{id}` (+ `check-status`) |
| Cancelamento | `DELETE` + justificativa (+ código municipal) | `DELETE` + `reason` |
| Artefatos | URLs no raw / download Focus | `.../pdf` e `.../xml` |
| Webhook | Header shared secret | Conta-level; **sem assinatura documentada** |
| Nacional | layout `nfsen` | `issueType=annfs` + campos NBS/CST/IBS |
| Multi-CNPJ | token Focus (conta) + CNPJ no body | key por empresa (modelo oficial) |
| Rate limit | não modelado no Hub | 60/min, 5/s |

---

## 3. Lacunas e riscos

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| R1 | Webhook **sem** assinatura documentada | Spoofing → autorização falsa | Confirmar com suporte Spedy; até lá: secret compartilhado custom, allowlist IP, ou só poll + `check-status` |
| R2 | Blog vs OpenAPI (1 token + CNPJ) | Design errado de multi-tenant | Implementar key-por-empresa; provar no sandbox |
| R3 | Cobertura municipal parcial | Tenant em cidade não integrada | Gate onboarding via `/cities`; fallback Focus |
| R4 | `integrationId` 36 chars | `idempotency_key` livre pode estourar | Usar `str(NfIssue.id)` |
| R5 | Certificado duplicado (Hub + Spedy) | UX/ops | Fluxo: upload Hub → push Spedy no provisionamento |
| R6 | Campo `focus_ref` no model | Nome acoplado a Focus | Persistir UUID Spedy em `focus_ref` **ou** ADR para `provider_ref` genérico (preferível em sprint dedicada) |
| R7 | `process_queued_issue` chama `build_focus_body` | Mapper Focus hardcoded | Extrair `build_provider_body(route)` sem alterar Focus |
| R8 | Prazo/cancelamento municipal | Cancel QA falha | Testar sandbox + documentar por IBGE |
| R9 | Rate 5 rps | Batch admin/poll | Backoff + jitter; preferir webhook |
| R10 | RTC IBS/CBS | Paridade com Focus `RTC_NFSEN_MODE` | Mapear `ibsCbs` + flag settings Spedy; testes stub |

**Cadastro self-service + certificado via API:** cobertos pela doc — **não** bloqueiam o contrato necessário; o bloqueio real atual é **segurança do webhook** e **prova de cobertura municipal/sandbox**.

---

## 4. Mapeamento de campos (Hub → Spedy)

| Domínio Hub | Campo Spedy |
|-------------|-------------|
| `NfIssue.id` | `integrationId` |
| `competence_date` | `effectiveDate` |
| `service.description` | `description` |
| `amount_cents / 100` | `total.invoiceAmount` |
| `resolved_params.iss_rate` (*100) | `total.issRate` (+ amounts se necessário) |
| `iss_retained` / tipo retenção | `total.issWithheld` (**a confirmar** nome exato no TotalDto) |
| `Customer` | `receiver.*` + `address.city.code` IBGE |
| `Provider.document` | implícito na API Key da company (não no body) |
| `ibge_code` prestação | `location.code` / `taxLocation` |
| `service.lc116_item` / `service_code` | `federalServiceCode` |
| `codigo_tributacao_nacional_iss` | `nationalTaxationCode` |
| `params.codigo_nbs` | `nbsCode` |
| RTC CST/cClass/indOp | `ibsCbs.cst` / `classification` / `operationIndicatorCode` |
| `tributacao_iss` | `taxationType` (enum Spedy) |
| Justificativa cancelamento | `reason` |

Mapper sugerido: `integrations/nfse/mappers.py` → `to_spedy_service_invoice(issue) -> dict` (espelho de `to_focus_nfsen`).

---

## 5. Esboço do adapter (não implementar agora)

```python
# Esboço — integrations/nfse/spedy.py (futuro)
class SpedyNfseProvider:
    kind = "spedy"

    def __init__(self, *, api_key: str, base_url: str, mode: str = "stub"):
        ...

    def emitir(self, *, payload: dict) -> NfseEmitResult:
        # POST /v1/service-invoices
        # external_ref = response.id (UUID Spedy)
        # status = map_status(response.status)  # tipicamente "enqueued" → polling
        ...

    def consultar(self, *, ref: str) -> NfseEmitResult:
        # GET /v1/service-invoices/{ref}
        ...

    def cancelar(self, *, ref: str, justificativa: str, codigo_cancelamento=None) -> NfseEmitResult:
        # DELETE /v1/service-invoices/{ref} {"reason": justificativa}
        # codigo_cancelamento: ignorar ou mapear se sandbox exigir
        ...
```

Clientes auxiliares (fora da porta mínima, como Focus empresas):

- `SpedyCompanyClient` — companies / settings / certificates  
- `SpedyWebhookClient` — CRUD webhooks da conta  
- `SpedyCitiesClient` — gate de município  

Factory (futuro):

```python
# se route.kind == "spedy":
#   return SpedyNfseProvider(api_key=tenant_secret, base_url=settings.NFSE_SPEDY_BASE_URL, mode=...)
```

Roteamento sugerido (espelho billing):

- `tenant.settings["nfse_provider"] = "spedy" | "focus"` **ou**
- `tenant.settings["nfse_provider_by_ibge"][ibge] = "spedy"`
- Sem override → manter Focus (default atual).

---

## 6. Estratégia de configuração

| Variável | Papel |
|----------|--------|
| `NFSE_DEFAULT_PROVIDER` | permanece `focus` até go-live Spedy |
| `NFSE_SPEDY_HTTP_MODE` | `stub` \| `http` |
| `NFSE_SPEDY_BASE_URL` | default sandbox `https://sandbox-api.spedy.com.br/v1` |
| `NFSE_SPEDY_MASTER_API_KEY` | key da empresa principal (provisionamento) |
| `NFSE_SPEDY_WEBHOOK_SECRET` | **placeholder** até Spedy documentar assinatura |
| `SPEDY_WEBHOOK_PUBLIC_URL` | URL Hub `POST /api/v1/webhooks/spedy-nfse` |

Secrets por tenant:

- `TenantSecret(provider="spedy", key_name="api_key")`
- opcional `spedy_company_id` em `tenant.settings` ou secret metadata

Não misturar key sandbox/prod na mesma conta.

---

## 7. Plano de implementação (sprints sugeridas — pós-aprovação PO)

1. **Spike sandbox (1–2 dias):** conta Plano Desenvolvedor; criar company; upload cert; `issueType=annfs`; emitir 1 NFS-e; webhook + pdf/xml; validar Atibaia; esclarecer auth do webhook e multi-key.
2. **ADR curto:** Spedy como segundo NFS-e provider; regra de seleção; decisão `provider_ref`.
3. **Adapter stub + testes unitários** (contrato `NfseProvider`, mapper, status map) — sem HTTP real.
4. **HTTP client + factory + settings**; provisionamento company/cert espelhando Focus empresas.
5. **Webhook ingest** + artefatos; manter poll como fallback.
6. **Homologação E2E** sandbox → feature flag por tenant → produção.

**Não** alterar adapter Focus nesta trilha.

---

## 8. Plano de testes

### 8.1 Unitário (obrigatório na entrega de código)

| Cenário | Tipo |
|---------|------|
| Mapper Hub → payload Spedy (SN + nacional + IBS stub) | unit |
| Map status Spedy → FSM Hub | unit |
| `SpedyNfseProvider` mode=`stub` emitir/consultar/cancelar | unit |
| Factory escolhe `spedy` via `tenant.settings` | unit |
| Idempotência: `integrationId == str(issue.id)` | unit |
| Webhook ingest (quando houver secret/estratégia) + inbox idempotente | unit |
| Artefatos: download mock pdf/xml → `NfArtifact` | unit |

### 8.2 Só sandbox real

| Cenário |
|---------|
| Criar empresa + recuperar `apiKey` uma vez |
| Upload PFX e emissão autorizada |
| Rejeição e re-POST mesmo `integrationId` |
| Cancelamento autorizado + motivo |
| Webhook delivery + retries (endpoint 500 proposital) |
| Rate limit 429 |
| Município Atibaia / lista `/cities` |
| `issueType=annfs` + campos NBS/IBS |
| Multi-empresa: key filha vs principal |

---

## 9. Decisão sugerida (para PO / engenharia)

| Pergunta | Resposta do estudo |
|----------|-------------------|
| Spedy cabe atrás de `NfseProvider`? | **Sim** |
| Self-service cadastro + certificado via API? | **Sim (documentado)** |
| Pode substituir Focus amanhã? | **Não** — falta prova sandbox, cobertura IBGE, segurança webhook, desacoplar `build_focus_body` / `focus_ref` |
| Próximo passo | Spike sandbox + ADR; só então adapter stub |

---

## 10. Referências internas Hub

- `integrations/nfse/port.py`, `focus.py`, `factory.py`, `router.py`, `mappers.py`, `empresas.py`
- `apps/issuance/services.py`, `polling.py`, `artifacts.py`, `focus_webhook.py`
- `Docs/Exeq_Hub_NFSe_Emission_Architecture_Reference.md`
- Acordo: `.cursor/rules/exeq-engineering-agreement.mdc`
