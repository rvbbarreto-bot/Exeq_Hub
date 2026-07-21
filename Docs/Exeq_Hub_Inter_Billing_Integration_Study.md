# EXEQ Hub — Estudo de Integração Banco Inter (Cobrança BolePix v3)

| Campo | Valor |
|-------|--------|
| Status | **1.0.0** — decisão de Sprint 5 |
| Data | 2026-07-20 |
| Fonte oficial | [developers.inter.co](https://developers.inter.co/) · [Cobrança BolePix](https://developers.inter.co/references/cobranca-bolepix) |
| Decisão PO | **Inter é o primeiro provider** de billing (antes de Asaas/C6) |

Este documento é a referência da fábrica para fechar o gap entre o adaptador atual (`integrations/payments/banks.py`) e o contrato real do Inter.

---

## 1. Decisão de produto

1. Provider default do Hub: `PAYMENT_DEFAULT_PROVIDER=inter`.
2. Produto de cobrança: **API Cobrança v3 (Boleto + Pix / BolePix)** — não confundir com API Pix Cob (cob/cobv do BCB).
3. Asaas e C6 permanecem na porta `PaymentGateway`, mas só após Inter E2E (registro → artefatos → webhook → `paid`).

---

## 2. Pré-requisitos comerciais e de conta

| Requisito | Detalhe |
|-----------|---------|
| Tipo de conta | **Somente Conta Digital PJ** (PF/MEI não têm API) |
| Cadastro | Internet Banking → Soluções / Nova Integração |
| Credenciais | `client_id` + `client_secret` |
| Certificado | Par `.crt` + `.key` (ou `.pfx` no SDK oficial); validade típica **1 ano** |
| Conta corrente | Header `x-conta-corrente` quando há múltiplas contas |
| Sandbox | Obrigatório antes de produção |

---

## 3. Autenticação (ponto crítico vs Hub atual)

O Inter **não** autentica com um Bearer token estático tipo Asaas.

### 3.1 Fluxo obrigatório

```
mTLS (cert+key)  +  OAuth2 client_credentials  →  access_token (~3600s)
                                                      ↓
                              Authorization: Bearer <access_token>
                              (+ x-conta-corrente opcional)
```

| Item | Produção | Sandbox |
|------|----------|---------|
| Base API | `https://cdpj.partners.bancointer.com.br` | `https://cdpj-sandbox.partners.uatinter.co` |
| Token | `POST /oauth/v2/token` | mesmo path na base sandbox |
| Body | `application/x-www-form-urlencoded` | idem |
| Campos | `client_id`, `client_secret`, `grant_type=client_credentials`, `scope=...` | idem |

### 3.2 Escopos mínimos (Cobrança)

| Escopo | Uso |
|--------|-----|
| `boleto-cobranca.write` | Emitir, cancelar, cadastrar webhook |
| `boleto-cobranca.read` | Consultar, PDF, listar, sumário, ler webhook |

Escopos Pix (`cob.*`, `pix.*`, `webhook.*`) são **outra API** (Pix Cob). Para BolePix via Cobrança v3, priorizar `boleto-cobranca.*`.

### 3.3 Gap atual no Hub

| Capacidade | Hub hoje | Necessário |
|------------|----------|------------|
| Token | `INTER_API_TOKEN` / `TenantSecret(api_token)` Bearer fixo (legado) | **`InterAuthClient`**: OAuth + cache ~55 min |
| Transporte | HTTP simples sem cert (legado) | **mTLS** em token + chamadas (`inter_mtls`) |
| Segredos | 1 token | `client_id`, `client_secret`, cert/key PEM ou path |

**Status:** `InterAuthClient` implementado (`integrations/payments/inter_auth.py`). Smoke sandbox depende de credenciais reais PJ.

---

## 4. API Cobrança v3 — superfície operacional

Base path: `/cobranca/v3/cobrancas`

| Método | Path | Escopo | Função Hub |
|--------|------|--------|------------|
| `POST` | `/` | write | Emitir cobrança → `Charge.registered` |
| `GET` | `/{codigoSolicitacao}` | read | Detalhe / reconciliar artefatos |
| `GET` | `/` | read | Coleção (reconciliação/batch) |
| `GET` | `/sumario` | read | Operacional |
| `GET` | `/{codigoSolicitacao}/pdf` | read | PDF binário → `StoredFile` / download Admin |
| `POST` | `/{codigoSolicitacao}/cancelar` | write | Cancelar (motivo enum) |
| `PATCH` | `/{codigoSolicitacao}` | write | Editar (vencimento/valor) — fase 2 |
| `PUT` | `/webhook` | write | Registrar URL de callback |
| `GET` | `/webhook` | read | Consultar webhook |
| `DELETE` | `/webhook` | write | Remover webhook |
| `POST` | `/webhook/callbacks/retry` | write | Reenvio de callbacks (até 50) |

Rate limit típico Cobrança: **~60 req/min** (sandbox menor em alguns endpoints).

---

## 5. Emissão — request

Contrato alinhado ao adaptador Hub (`_inter_charge_body`):

```json
{
  "seuNumero": "máx 15 chars (usar recorte do charge.id)",
  "valorNominal": 150.50,
  "dataVencimento": "2026-08-01",
  "numDiasAgenda": 0,
  "pagador": {
    "cpfCnpj": "52998224725",
    "nome": "Pagador",
    "tipoPessoa": "FISICA"
  },
  "mensagem": { "linha1": "Descrição até 80 chars" }
}
```

### Campos importantes (evolução)

| Campo | Obrigatório? | Nota |
|-------|--------------|------|
| `seuNumero` | Sim | Identificador do lojista; **não** é o `codigoSolicitacao` |
| `valorNominal` | Sim | Decimal reais (Hub armazena `amount_cents`) |
| `dataVencimento` | Sim | `YYYY-MM-DD` |
| `numDiasAgenda` | Sim (0+) | Dias após vencimento em carteira |
| `pagador.cpfCnpj` / `nome` / `tipoPessoa` | Sim | `FISICA` \| `JURIDICA` |
| `pagador.email`, endereço, CEP | Recomendado | Algumas rotinas/bancos exigem endereço completo |
| `desconto`, `multa`, `mora` | Opcional | Fase 2 |
| `formasRecebimento` | Conforme doc | Controla boleto vs pix vs ambos (BolePix) |

Header recomendado: `x-idempotency-key` (já enviado pelo Hub).

---

## 6. Emissão — response e artefatos

A **criação** pode retornar só `{ "codigoSolicitacao": "<uuid>" }`.  
Artefatos completos costumam vir no **GET detalhe** / listagem:

```json
{
  "cobranca": {
    "codigoSolicitacao": "183e982a-...",
    "seuNumero": "SN12345",
    "situacao": "A_RECEBER",
    "valorNominal": 500.00,
    "dataVencimento": "2023-10-31",
    "boleto": {
      "nossoNumero": "...",
      "codigoBarras": "...",
      "linhaDigitavel": "..."
    },
    "pix": {
      "txid": "...",
      "pixCopiaECola": "00020126..."
    }
  }
}
```

| Artefato Inter | Campo Hub sugerido |
|----------------|--------------------|
| `codigoSolicitacao` | `Charge.gateway_ref` |
| `boleto.linhaDigitavel` | `digitable_line` |
| `boleto.codigoBarras` | `barcode` |
| `pix.pixCopiaECola` | `pix_copy_paste` |
| `GET .../pdf` | `StoredFile` + link Admin (não há URL pública permanente tipicamente) |
| raw | `gateway_payload` |

**Regra de implementação:** após `POST`, se não houver linha digitável, fazer `GET /{codigoSolicitacao}` (com retry curto) antes de marcar `registered` completo.

---

## 7. Situações (status Inter → Hub)

| `situacao` Inter | Ação Hub |
|------------------|----------|
| `EM_PROCESSAMENTO` | Manter `pending`/`registered`; poll/webhook |
| `A_RECEBER` | `registered` |
| `RECEBIDO` / `MARCADO_RECEBIDO` | `PaymentEvent` → `paid` |
| `ATRASADO` | `overdue` |
| `CANCELADO` | `cancelled` |
| `EXPIRADO` | `cancelled` ou `failed` (definir regra) |
| `FALHA_EMISSAO` | `failed` |
| `PROTESTO` | Operacional / fase 2 |

**DoD Sprint 5:** `paid` **somente** via `PaymentEvent` + `WebhookInbox` (já no domínio Hub).

---

## 8. Cancelamento

```
POST /cobranca/v3/cobrancas/{codigoSolicitacao}/cancelar
{ "motivoCancelamento": "ACERTOS" }
```

Motivos documentados incluem enums como `ACERTOS`, `CLIENTE_DESISTIU`, etc.  
Resposta típica `202` com status `PROCESSANDO` — cancelamento **assíncrono**; confirmar via webhook ou GET.

Hub hoje: `INTER_CANCEL_MOTIVO=ACERTOS` (ok para default).

---

## 9. Webhook Cobrança

### 9.1 Cadastro

```
PUT /cobranca/v3/cobrancas/webhook
{ "webhookUrl": "https://hub.../api/v1/webhooks/gateway" }
```

URL deve ser **HTTPS** pública. Reenvio: `POST .../webhook/callbacks/retry` com lista de `codigoSolicitacao`.

### 9.2 Assinatura

O Hub valida HMAC com `WEBHOOK_GATEWAY_SECRET` (`X-Webhook-Signature`).  
O Inter Cobrança **não** usa o mesmo esquema Asaas por padrão — validar no portal o mecanismo oficial (certificado cliente, IP allowlist, ou header próprio).

**Gap:** normalizer atual cobre canônico Hub + Asaas-like; **falta parser Inter** (`situacao`, `codigoSolicitacao`, valor, data).

### 9.3 Payload canônico Hub (alvo)

```json
{
  "provider": "inter",
  "idempotency_key": "RECEBIDO:<codigoSolicitacao>:<dataSituacao>",
  "gateway_ref": "<codigoSolicitacao>",
  "amount_cents": 50000,
  "paid_at": "2026-07-20T15:00:00-03:00",
  "external_reference": "<seuNumero ou charge.id>",
  "event": "RECEBIDO"
}
```

Se o callback Inter for “leve” (só código), o processador deve **GET detalhe** antes de criar `PaymentEvent`.

---

## 10. Sandbox vs produção

| | Sandbox | Produção |
|--|---------|----------|
| Base | `cdpj-sandbox.partners.uatinter.co` | `cdpj.partners.bancointer.com.br` |
| Cert/chaves | Integração de teste no IB | Integração produção |
| Pagamento simulado | Ferramentas/sandbox do portal | Real |
| Rate limit | Mais restrito | ~60/min Cobrança |

---

## 11. Mapa Hub atual × contrato Inter

| Item | Status |
|------|--------|
| Path emitir/cancelar | OK (`INTER_CHARGE_PATH` / cancel tmpl) |
| Body mínimo emitir | OK (enriquecer endereço/email) |
| Stub mode | OK |
| Default provider | **→ `inter`** (esta entrega) |
| OAuth + mTLS | **Falta** |
| Persistência artefatos | Campos no model em andamento; service ainda não grava |
| GET detalhe pós-emissão | **Falta** |
| GET PDF → StoredFile | **Falta** |
| Normalize webhook Inter | **Falta** |
| PUT webhook na ativação do tenant | **Falta** |
| Admin linha digitável / PDF | **Falta** |

---

## 12. Fatias de implementação (Sprint 5 — Inter first)

1. **Auth Inter** — `client_id`/`secret` + cert/key por tenant; cache de token; httpx mTLS.
2. **Emitir + enriquecer** — POST → GET detalhe → gravar `gateway_ref`, linha, barras, PIX, payload.
3. **PDF** — GET pdf → `StoredFile` + ação Admin/API download.
4. **Webhook** — normalizer Inter + inbox + `paid` só com valor compatível.
5. **Ops** — registrar webhook URL; retry callbacks; smoke sandbox.
6. **Depois** — Asaas / C6 com o mesmo contrato de artefatos.

---

## 13. Segredos sugeridos (`TenantSecret`)

| `provider` | `key_name` |
|------------|------------|
| `inter` | `client_id` |
| `inter` | `client_secret` |
| `inter` | `cert_pem` |
| `inter` | `key_pem` |
| `inter` | `conta_corrente` (opcional) |

Env global (dev): `INTER_CLIENT_ID`, `INTER_CLIENT_SECRET`, `INTER_CERT_PATH`, `INTER_KEY_PATH`, `INTER_CONTA_CORRENTE`.

Deprecar progressivamente `INTER_API_TOKEN` (não reflete o modelo OAuth+mTLS).

---

## 14. Referências

- Portal: https://developers.inter.co/
- Cobrança BolePix: https://developers.inter.co/references/cobranca-bolepix
- API Banking marketing: https://inter.co/empresas/api-banking/
- Ajuda PJ APIs: https://ajuda.inter.co/conta-digital-pessoa-juridica/o-inter-disponibiliza-alguma-api-para-minha-conta-digital-pj
- SDK oficial (Java/C#/Python no portal) — útil como espelho de modelos; Hub mantém adaptador próprio na porta `PaymentGateway`

---

## 15. Critério de aceite (PO)

- [ ] Default `inter` em stub e HTTP.
- [ ] Cobrança registrada no sandbox com `codigoSolicitacao` + linha digitável + PIX (se BolePix).
- [ ] PDF baixável no Admin.
- [ ] Webhook `RECEBIDO` → `Charge.paid` via `PaymentEvent` idempotente.
- [ ] Sem chamar Asaas no caminho feliz do tenant default.
