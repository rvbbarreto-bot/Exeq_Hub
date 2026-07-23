# EXEQ Hub — Estudo de Integração C6 Bank Empresas (Boleto Cobrança BaaS)

| Campo | Valor |
|-------|--------|
| Status | **0.9.0-draft** — estudo técnico pré-implementação |
| Data | 2026-07-21 |
| Fontes | [developers.c6bank.com.br](https://developers.c6bank.com.br/) · [APIs C6](https://www.c6bank.com.br/apis-integracao/) · BaaS `baas-api*.c6bank.info` · SDKs/integradores públicos (divulgueregional, Fluid) |
| Decisão PO (contexto) | Inter é o 1º provider E2E; C6 é o próximo banco nativo na porta `PaymentGateway` |
| Aviso | OpenAPI completa do portal C6 é **contract-gated**. Endpoints abaixo foram triangulados com libs que citam o “Guia C6” + respostas reais de emissão. **Validar 1:1 no portal após onboarding.** |

Este documento é a referência da fábrica para fechar o gap entre o scaffold atual (`C6PaymentGateway` + Bearer estático) e o contrato real do C6 BaaS (OAuth2 + mTLS + `bank_slips`).

---

## 1. Decisão de produto (recomendação tech lead)

1. Produto alvo fase 1: **API Boleto Cobrança BaaS** (`/v1/bank_slips`) — emissão, consulta, PDF, cancelamento, alteração.
2. **Não** misturar com API Pix BCB (`/v2/pix/cob|cobv`) na mesma sprint: Pix C6 é família separada (útil depois para cobrança instantânea / híbrido).
3. Boleto híbrido com QR Pix **no PDF do boleto**: integradores reportam **não disponível** no C6 — não prometer BolePix-like como no Inter.
4. Reutilizar a porta `PaymentGateway` já usada pelo Inter; **não** forçar o domínio `apps/billing` a conhecer payloads C6.
5. Credenciais por tenant (mesmo padrão Inter): `TenantSecret` + env de fallback.

---

## 2. Pré-requisitos comerciais e de conta

| Requisito | Detalhe |
|-----------|---------|
| Tipo de conta | **Conta PJ C6 Empresas** (Web Banking PJ — não App Mobile PF) |
| Produto | Liberação de **Boleto Cobrança via API** (gerente / atendimento) |
| Cadastro portal | [developers.c6bank.com.br](https://developers.c6bank.com.br/) — área de atuação + produtos de interesse |
| Credenciais | Geradas em **Meu Perfil → Integrações via API → Nova chave** |
| Permissões da chave | Produto **Boleto de cobrança** + emissão, consulta, baixa/cancelamento, atualização |
| Material entregue | `ClientId`, `ClientSecret`, **certificado** (download **uma única vez**) |
| Homologação | Sandbox obrigatório antes de produção; ERP pode passar certificação parceiro C6 |

### Processo operacional (obrigatório no runbook)

1. Criar chave no Web Banking (não no app).
2. Baixar o pacote de certificado **sem descompactar de forma destrutiva** — tipicamente `cert.crt` + `cert.key` (ou ZIP com o par).
3. Converter para PEM armazenável no Hub se necessário; opcional PFX só para terceiros (PlugBoleto etc.).
4. Renovação: certificado/chave **expiram** (relatos de ciclo ~1 ano) — criar nova chave + novo cert; planejar alerta de vencimento.

---

## 3. Autenticação (ponto crítico vs Hub atual)

O C6 **não** autentica com um Bearer token estático tipo Asaas. O padrão observado (alinhado ao Inter) é:

```
mTLS (cert.crt + cert.key)
  +  OAuth2 client_credentials  →  access_token
                                        ↓
              Authorization: Bearer <access_token>
              + mTLS em TODAS as chamadas
              + headers partner-software-*
```

### 3.1 Ambientes

| Ambiente | Base URL |
|----------|----------|
| Sandbox | `https://baas-api-sandbox.c6bank.info` |
| Produção | `https://baas-api.c6bank.info` |

### 3.2 Token

| Item | Valor |
|------|--------|
| Método / path | `POST /v1/auth` |
| Content-Type | `application/x-www-form-urlencoded` |
| Body | `grant_type=client_credentials` + `client_id` + `client_secret` |
| Transporte | **mTLS obrigatório** (mesmo cert da chave) |
| Resposta | `access_token`, `expires_in` / expiry, `token_type=Bearer` |

### 3.3 Headers de parceiro (recomendado em todas as calls)

| Header | Uso |
|--------|-----|
| `partner-software-name` | Identificação do ERP (ex.: `EXEQ Hub`) |
| `partner-software-version` | SemVer do Hub (ex.: `4.1.0`) |

Úteis para suporte C6 e auditoria de parceiro.

### 3.4 Gap atual no Hub

| Capacidade | Hub hoje | Necessário |
|------------|----------|------------|
| Auth | `C6_API_TOKEN` / `TenantSecret(api_token)` Bearer fixo | **`C6AuthClient`**: OAuth `/v1/auth` + cache com skew |
| Transporte | HTTP sem cert | **mTLS** em token + `bank_slips` (reusar padrão `inter_mtls`) |
| Segredos | 1 token | `client_id`, `client_secret`, `cert_pem`/`key_pem` (ou paths) |
| Factory | `TOKEN_PROVIDERS` inclui `c6` | Tratar C6 como **provider OAuth+mTLS** (irmão do Inter), não Asaas |
| Partner headers | ausentes | `C6_PARTNER_SOFTWARE_NAME` / `VERSION` |

**Conclusão:** o scaffold `C6PaymentGateway` cobre path/body básicos, mas **não é production-ready** enquanto a auth for Bearer estático.

---

## 4. Superfície operacional — Boleto (`bank_slips`)

Base: `/v1/bank_slips`

| Método | Path | Função Hub |
|--------|------|------------|
| `POST` | `/v1/bank_slips` | Emitir → `Charge.registered` + artefatos |
| `GET` | `/v1/bank_slips/{id}` | Sync / reconciliar status e artefatos |
| `GET` | `/v1/bank_slips/{id}/pdf` | PDF binário → download Admin / `StoredFile` |
| `PUT` | `/v1/bank_slips/{id}/cancel` | Cancelar (baixa) → `cancelled` |
| `PUT` | `/v1/bank_slips/{id}` | Alterar (vencimento/valor/etc.) — fase 2 |

Hub já aponta emissão/cancel para esses paths (`C6_CHARGE_PATH`, `C6_CANCEL_PATH_TMPL`). Falta consulta dedicada + PDF + mapeamento de status C6.

### 4.1 Família Pix (fora do escopo boleto fase 1)

| Path | Nota |
|------|------|
| `POST /v2/pix/cob` | Cobrança imediata |
| `PUT /v2/pix/cobv/{txid}` | Pix com vencimento |
| `PUT/GET/DELETE /v2/pix/webhook/{chave}` | Webhook Pix (padrão BCB) |

Usar depois se o produto quiser Pix puro C6; **não** confundir com boleto.

---

## 5. Emissão — request

Contrato alinhado ao adaptador Hub (`_c6_charge_body`) e a conectores (Fluid):

```json
{
  "external_reference_id": "máx ~64 (idempotência de negócio / charge id)",
  "amount": 100.50,
  "due_date": "2026-08-01",
  "instructions": ["Não receber após o vencimento"],
  "billing_scheme": "21",
  "our_number": "10203286",
  "payer": {
    "name": "João da Silva",
    "tax_id": "12345678900",
    "email": "opcional@exeq.com",
    "address": {
      "street": "Rua das Flores",
      "number": "123",
      "city": "Florianópolis",
      "state": "SC",
      "zip_code": "88000000",
      "complement": "opcional"
    }
  }
}
```

### 5.1 Campos críticos

| Campo | Obrigatório | Nota Hub |
|-------|-------------|----------|
| `external_reference_id` | Sim | Mapear de `idempotency_key` / `charge.id` (único por tenant) |
| `amount` | Sim | Reais com 2 casas (centavos Hub → `/100`) |
| `due_date` | Sim | `YYYY-MM-DD`; aplicar regras Hub (não passado; após 16h → D+1) |
| `payer.name` / `tax_id` | Sim | CPF/CNPJ só dígitos |
| `payer.address.*` | Sim (CEP, rua, nº, cidade, UF) | Endereço do Customer — **não** depender só de defaults env |
| `billing_scheme` | Quase sempre | **`21` sandbox / `15` produção** (já em `C6_BILLING_SCHEME`) |
| `instructions` | Não | Até **4** linhas (Hub hoje manda 1 truncada em 80) |
| `our_number` | Condicional | Nosso número; validar regras do convênio C6 (não inventar fora do range) |

### 5.2 Multa / juros / desconto

Presets Hub (`num_dias_agenda`, `multa_percent`, `mora_percent_am`) estão modelados no domínio Inter. **No body C6 atual do Hub esses campos não são enviados.**

Ação: no portal OpenAPI, localizar nomes oficiais (ex. `fine`, `interest`, `discount`, `days_to_protest`) e mapear em `_c6_charge_body` a partir de `charge_options`. Sem OpenAPI, **não inventar** — homologar com payload mínimo e evoluir.

### 5.3 Resposta típica (emissão)

```json
{
  "id": "01KQWMVPR4XMDC3DHAGPCHKWN1",
  "amount": 100.5,
  "due_date": "2026-06-10",
  "originator_id": "000006441036",
  "our_number": "10203286",
  "billing_scheme": "21",
  "billing_type": "3",
  "bar_code": "33695...",
  "digitable_line": "33690.00009 ..."
}
```

| Campo C6 | Campo Hub |
|----------|-----------|
| `id` | `Charge.gateway_ref` |
| `digitable_line` | `digitable_line` (já coberto em `extract_boleto_artifacts`) |
| `bar_code` | `barcode` — **atenção:** Hub procura `barcode`/`barCode`; incluir alias `bar_code` |
| `our_number` | `extras.our_number` / auditoria |
| PDF | `GET .../pdf` (não vem URL estática na emissão) |

---

## 6. Consulta, cancelamento, alteração

### 6.1 Consulta (`GET /v1/bank_slips/{id}`)

Base do `sync_charge_from_gateway`. Hoje o Hub reutiliza **`map_inter_situacao` / `inter_artifacts`** — **incorreto para C6**.

Entregar:

- `c6_status.py` com mapa oficial de status (valores exatos só após OpenAPI; esboço operacional):

| Situação C6 (hipótese a validar) | Status Hub |
|----------------------------------|------------|
| registered / open / pending / emitted | `registered` |
| paid / settled / liquidated | `paid` |
| cancelled / canceled / written_off | `cancelled` |
| expired / overdue (sem baixa) | `registered` ou `overdue` se o domínio criar o estado |

Guardar `raw` completo em `gateway_payload` para reconciliação.

### 6.2 Cancelamento (`PUT .../cancel`)

- Sem body de motivo no padrão observado (diferente do Inter `motivoCancelamento`).
- **Remover** validação `INTER_CANCEL_MOTIVOS` do caminho compartilhado quando `provider=c6`.

### 6.3 Alteração (`PUT /v1/bank_slips/{id}`) — fase 2

Útil para mudança de vencimento/valor antes do pagamento. Expor só depois de regras de negócio (bloqueio se pago).

---

## 7. Webhooks e liquidez

| Canal | Situação |
|-------|----------|
| Pix webhook (`/v2/pix/webhook`) | Documentado em libs; **não cobre boleto** |
| Webhook boleto BaaS | **Confirmar no portal** — muitos ERPs fazem **polling** de `GET bank_slips/{id}` + job de sync |
| Hub atual | `POST /api/v1/webhooks/gateway` com HMAC genérico; normalizer **sem** shape nativo C6 |

### Recomendação robusta

1. Fase 1: **sync sob demanda** (já existe) + **job periódico** por tenant C6 (charges `registered`).
2. Fase 2: se C6 publicar webhook de boleto, adicionar `normalize_c6_payload` + verificação de assinatura específica.
3. Idempotência: `WebhookInbox` por `provider=c6` + chave de evento; criar `PaymentEvent` só se valor bater.

---

## 8. Gap analysis Hub × contrato C6

| # | Item | Hub hoje | Alvo |
|---|------|----------|------|
| 1 | Auth OAuth+mTLS | Bearer estático | `C6AuthClient` espelhando Inter |
| 2 | Credenciais tenant | `api_token` | `client_id`, `client_secret`, cert/key |
| 3 | `billing_scheme` | env default `21` | Auto por ambiente (sandbox→21, prod→15) + override |
| 4 | Endereço pagador | fallbacks env genéricos | Obrigatório do `Customer` (validar no domínio) |
| 5 | Artefato `bar_code` | alias incompleto | Incluir `bar_code` em `boleto.py` |
| 6 | PDF | não busca | `GET .../pdf` + Admin download |
| 7 | Sync status | mapa Inter | `c6_status.map_c6_situacao` |
| 8 | Multa/juros | não envia | Mapear após OpenAPI |
| 9 | Instructions | 1 linha | até 4 linhas a partir de `message_lines` |
| 10 | Cancel motivos | enum Inter no service | Motivo só quando provider=inter |
| 11 | Partner headers | ausentes | name/version EXEQ |
| 12 | Test connection | só Inter | `POST /billing/providers/c6/test-connection` |
| 13 | Webhook nativo | não | Polling + opcional webhook fase 2 |
| 14 | BolePix no PDF | N/A | Fora de escopo C6 |

---

## 9. Arquitetura alvo no Hub

```
apps/billing (create/sync/cancel)
        ↓
PaymentGateway Protocol
        ↓
C6PaymentGateway
        ↓
C6AuthClient (token cache + mTLS)
        ↓
https://baas-api[-sandbox].c6bank.info
```

### Módulos a criar/alterar

| Módulo | Ação |
|--------|------|
| `integrations/payments/c6_auth.py` | Novo — espelho de `inter_auth.py` (`POST /v1/auth`) |
| `integrations/payments/c6_mtls.py` ou reuso `inter_mtls` | Compartilhar builder SSLContext PEM/path |
| `integrations/payments/c6_status.py` | Novo — status + artefatos |
| `integrations/payments/banks.py` | `C6PaymentGateway._request` via auth; body rico |
| `integrations/payments/factory.py` | Resolver credenciais OAuth C6 |
| `apps/billing/provider_services.py` | Tirar C6 de `TOKEN_PROVIDERS`; CRUD estilo Inter |
| `apps/billing/services.py` | Cancel/sync sem hardcode Inter |
| `integrations/payments/boleto.py` | Alias `bar_code` |
| Testes | Auth unit + HTTP contract (VCR/httpx mock) + E2E sandbox |

---

## 10. Plano de entrega (sprints sugeridas)

### Sprint A — Fundamentos (bloqueante)

1. Onboarding conta PJ + chave API + cert no sandbox.
2. `C6AuthClient` + test-connection.
3. Emitir 1 boleto sandbox e capturar request/response reais → congelar fixtures.
4. Corrigir artefatos (`bar_code`, `id` → `gateway_ref`).

### Sprint B — Ciclo de vida

1. Consulta + mapa de status + sync Admin/API.
2. Cancelamento sem motivos Inter.
3. PDF download.
4. Validação de endereço/valor/vencimento no domínio antes do POST.

### Sprint C — Robustez

1. Multa/juros/desconto (OpenAPI).
2. Job de polling de liquidações.
3. Webhook nativo se existir.
4. Runbook de renovação de certificado + alertas.

### Critérios de pronto (DoD)

- [ ] Token renovado automaticamente com skew.
- [ ] Emissão sandbox retorna linha digitável + código de barras persistidos.
- [ ] Sync marca `paid` após liquidação (manual ou webhook).
- [ ] Cancel idempotente.
- [ ] Segredos só em `TenantSecret` / vault; nunca commit.
- [ ] Suite unitária sem rede + 1 smoke sandbox documentado.

---

## 11. Riscos e mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| OpenAPI gated / divergência de path | Retrabalho | Congelar contrato com fixtures reais pós-1ª emissão |
| Cert one-time download perdido | Bloqueio total | Backup cifrado + processo de reemissão de chave |
| `billing_scheme` errado (15 vs 21) | Rejeição / boleto inválido | Derivação automática por `C6_API_BASE_URL` |
| Assumir BolePix | Expectativa de produto falsa | Documentar “boleto puro”; Pix = API aparte |
| Polling sem webhook | Delay de baixa | Job curto (ex. 5–15 min) + sync manual |
| Endereço default “NAO INFORMADO” | Recusa CIP/registradora | Falhar cedo se Customer sem endereço completo |
| Vazamento de padrões Inter no domínio | Bugs em cancel/sync | Branch por `gateway.kind` / strategy objects |

---

## 12. Checklist de homologação (sandbox)

1. `POST /v1/auth` com mTLS → 200 + `access_token`.
2. `POST /v1/bank_slips` valor ≥ mínimo do convênio, vencimento D+1, pagador com endereço real.
3. Conferir `id`, `digitable_line`, `bar_code` no Internet Banking C6.
4. `GET /v1/bank_slips/{id}` bate com Hub após sync.
5. `GET .../pdf` abre PDF legível.
6. `PUT .../cancel` reflete cancelado no banking e no Hub.
7. (Opcional) liquidar boleto de teste e validar caminho `paid`.

---

## 13. Referências

- Portal: https://developers.c6bank.com.br/
- Marketing APIs: https://www.c6bank.com.br/apis-integracao/
- Hub Inter (padrão a espelhar): `Docs/Exeq_Hub_Inter_Billing_Integration_Study.md`
- Código atual: `integrations/payments/banks.py` (`C6PaymentGateway`), `factory.py`, `.env.example` (`C6_*`)
- Evidência de paths: biblioteca `divulgueregional/api-c6-bank` (Guia C6); conector Fluid (campos + response sample)

---

## 14. Próximo passo imediato

1. **PO / ops:** liberar produto API + gerar chave sandbox + entregar cert ao cofre do Hub.
2. **Eng:** implementar `C6AuthClient` (cópia controlada do padrão Inter) e um smoke `manage.py`/pytest marcado `sandbox`.
3. **Tech lead:** só então expandir body (multa/juros) e job de sync — evitar construir em cima de Bearer estático.
