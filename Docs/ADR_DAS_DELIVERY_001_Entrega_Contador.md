# ADR-DAS-DELIVERY-001 — Entrega de Guia DAS/DARF ao Contador (E-mail + WhatsApp)

| Campo | Valor |
|-------|--------|
| Status | **Aprovado — implementado v1** (PO 2026-09-08) |
| Versão | **1.0.0** |
| Decisores | PO, Tech Lead, Engenharia Fiscal |
| Relacionado | v1 §Guias DAS/DARF · v2 §Outbox · ARD WhatsApp NFSe §11 · RF-71 NF-e e-mail · RF-72 NF-e WhatsApp |
| Escopo v1 | Entrega automática pós-`DISPONIVEL` · reenvio via outbox · preferências Hub · API resend |
| Fora v1 | Papel `accountant` · pacote ZIP competência · CC múltiplo · grupo WhatsApp · Meta Cloud obrigatório · política DARF separada |

---

## 1. Contexto

### 1.1 Situação atual

O EXEQ Hub **captura e persiste** guias DAS/DARF (`apps/das/services.emitir_guia`):

- PDF em `StoredFile` (`purpose=das_pdf`, chave `das/{tenant}/{tipo}/{cnpj}/{competencia}/…pdf`)
- Modelo `GuiaFiscal` com status `DISPONIVEL`, valores, linha digitável, PIX
- Download autenticado via API (`GET /api/v1/das/guias/{id}/pdf/`)
- Outbox `guia_fiscal.available` → **apenas texto** para `tenant.settings.notify_phone` (ops), **sem PDF**, **sem e-mail**, **sem destinatário contador**

O contador (escritório de contabilidade) precisa receber o **PDF** e os **dados de pagamento** (vencimento, linha digitável, PIX) para conferência e orientação ao cliente — sem depender de login no Hub.

### 1.2 Referências internas

| Peça existente | Uso neste ADR |
|----------------|---------------|
| `apps/nfe/email_delivery.py` (RF-71) | Padrão de e-mail com anexo + idempotência + falha isolada |
| `apps/channel/services.deliver_nfe_artifacts` (RF-72) | Padrão WhatsApp mídia + `ChannelNotification` |
| `apps/ops/dispatcher.claim_and_dispatch` | Barramento assíncrono com retry (8 tentativas) |
| `Docs/Exeq_Hub_ARD_WhatsApp_NFSe_Mensageria.md` §11 | Entrega por **anexo**; sem URL pública de artefato |

### 1.3 Decisões de produto (PO — 2026-09-08)

| # | Tema | Decisão |
|---|------|---------|
| D-01 | Fallback `nfe_notify_email` | **Opção C** — só se `use_nfe_notify_email_for_das: true` |
| D-02 | Ops paralelo | **Opção C** — ops texto curto; contador PDF + PIX/linha digitável |
| D-03 | DARF | **Opção A** — mesma política que DAS |
| D-04 | WhatsApp produção | **Evolution** (piloto/comercial inicial) |
| D-05 | Reenvio | **Sempre outbox** (paridade RF-71/72) |
| D-06 | Destinatários | **Um e-mail + um WhatsApp** (`accountant_email`, `accountant_whatsapp`) |

---

## 2. Decisão

Implementar **entrega documental DAS/DARF ao contador** como extensão do fluxo outbox existente, **sem alterar** a regra fiscal de emissão/captura e **sem bloquear** `GuiaFiscal.status` em caso de falha de canal.

### 2.1 Princípios

| ID | Decisão |
|----|---------|
| DD-01 | Emissão/captura Receita **commitada antes** da entrega; delivery é side-effect assíncrono |
| DD-02 | Falha de e-mail ou WhatsApp **não altera** status da guia (`DISPONIVEL` permanece) |
| DD-03 | PDF lido de `StoredFile` via storage abstraction; **nunca** URL pública |
| DD-04 | DAS e DARF compartilham **mesma política**; diferença apenas no rótulo (assunto/caption) |
| DD-05 | Ops (`notify_phone`) recebe **somente texto**; contador recebe **PDF + metadados** |
| DD-06 | Reenvio manual (Hub/API) **sempre via outbox**; UI informa “enfileirado” |
| DD-07 | Idempotência por guia + canal + destinatário; retry outbox não duplica anexos |
| DD-08 | Camadas: View → Serializer → App Service (`das/delivery`) → Outbox → Dispatcher → integrations |
| DD-09 | WhatsApp v1 via **Evolution** (`integrations/evolution`); gateway dual permanece para migração futura Meta |
| DD-10 | v1: **um** e-mail To e **um** número WhatsApp; sem CC/lista |

---

## 3. Arquitetura

### 3.1 Fluxo

```
emitir_guia()
  → GuiaFiscal.status = DISPONIVEL
  → enqueue_outbox("guia_fiscal.available", aggregate_id=guia.id)
        │
        ▼
claim_and_dispatch (Celery)
  → _notify_guia_available (estendido)
        │
        ├─► [Ops] enqueue_notification(notify_phone)
        │         corpo: 1 linha (CNPJ, competência, total, "enviado ao contador")
        │         SEM PDF
        │
        └─► deliver_guia_to_accountant(guia)  [novo]
              ├─► deliver_guia_email()     → Django EmailMessage + PDF
              └─► deliver_guia_whatsapp()  → enqueue_media_notification (Evolution)
```

### 3.2 Reenvio

```
Hub/API: POST …/resend-delivery/  { "channels": ["email","whatsapp"], "force": true }
  → enqueue_outbox("guia_fiscal.redelivery_requested", payload={ force, channels })
  → mesmo handler de entrega com force=True (ignora flags sent)
  → resposta HTTP 202 Accepted + mensagem "Reenvio enfileirado"
```

### 3.3 Componentes (alvo de implementação)

| Peça | Local proposto | Responsabilidade |
|------|----------------|------------------|
| Resolução destinatários | `apps/das/delivery.py` | E-mail/WhatsApp contador + regras fallback |
| E-mail | `apps/das/delivery.py` | Anexo PDF, corpo com PIX/linha digitável |
| WhatsApp contador | `apps/das/delivery.py` | Texto + PDF via `enqueue_media_notification` |
| Ops alert | `apps/ops/dispatcher.py` | Texto curto em `notify_phone` |
| Outbox emit | `apps/das/services.py` | Mantém `guia_fiscal.available` |
| Preferências | Hub V4 `preferences` ou seção DAS | Campos contador + flag fallback |
| API resend | `apps/das/views.py` | Action `resend_delivery` |
| Hub detail | `hub_v4/das/detail.html` | Status entrega + botão reenviar + download PDF |

**Não criar** novo Domain Engine (v2 §5). Delivery é application service + handlers outbox.

---

## 4. Configuração (`tenant.settings`)

### 4.1 Schema

```json
{
  "das_delivery": {
    "enabled": true,
    "email_auto": true,
    "whatsapp_auto": true,
    "accountant_email": "contador@escritorio.com.br",
    "accountant_whatsapp": "+5511987654321",
    "use_nfe_notify_email_for_das": false,
    "include_pix_in_message": true,
    "include_linha_digitavel_in_message": true
  },
  "nfe_notify_email": "fiscal@escritorio.com.br",
  "notify_phone": "+5511999999999",
  "whatsapp_provider": "evolution"
}
```

### 4.2 Resolução de e-mail (ordem)

1. `payload.delivery_email` (override na emissão/API resend)
2. `das_delivery.accountant_email`
3. Se vazio **e** `das_delivery.use_nfe_notify_email_for_das === true` → `nfe_notify_email`
4. Caso contrário → **noop** (sem exceção; log `das_delivery_no_email_recipient`)

### 4.3 Resolução de WhatsApp contador (ordem)

1. `payload.delivery_phone`
2. `das_delivery.accountant_whatsapp`
3. **Sem fallback** para `notify_phone` (reservado a ops)
4. Vazio → noop

### 4.4 Ops (`notify_phone`)

- Disparo **independente** de `das_delivery.enabled`
- **Somente** `enqueue_notification` (texto)
- Não recebe PDF

---

## 5. Conteúdo das mensagens

### 5.1 E-mail (contador)

**Assunto:** `{DAS|DARF} {competencia} · CNPJ {document} · {legal_name}`

**Corpo (texto plano v1):**

- Razão social e CNPJ do `provider`
- Tipo de guia, competência, versão
- Valores: principal, multa, juros, **total**
- Data de vencimento (se houver)
- Linha digitável e PIX copia e cola (se `include_*` true)
- ID interno da guia (UUID) para suporte

**Anexo:** `guia-{DAS|DARF}-{competencia}-{cnpj}.pdf` (bytes de `guia.pdf_file`)

### 5.2 WhatsApp contador (Evolution)

1. Mensagem texto (mesmos metadados do e-mail, resumidos)
2. Documento PDF (`send_media`, `mediatype=document`)

### 5.3 WhatsApp ops

Exemplo:

```
DAS 2026-07 · CNPJ 45578450000102 · Total R$ 150,75 · Enviado ao contador.
```

---

## 6. Idempotência e auditoria

### 6.1 Flags em `GuiaFiscal.metadata.delivery`

```json
{
  "delivery": {
    "email_sent": true,
    "email_to": "contador@escritorio.com.br",
    "email_at": "2026-09-08T14:30:00Z",
    "whatsapp_sent": true,
    "whatsapp_to": "+5511987654321",
    "whatsapp_at": "2026-09-08T14:30:05Z",
    "last_error": "",
    "last_resent_at": null
  }
}
```

### 6.2 Regras

| Cenário | Comportamento |
|---------|---------------|
| Retry outbox sem `force` | Não reenvia canal já `*_sent=true` |
| Reenvio Hub/API com `force=true` | Reenvia canais solicitados; atualiza `last_resent_at` |
| Emissão idempotente (mesmo `idempotency_key`) | Retorna guia existente; **não** re-dispara delivery se já sent |
| PDF ausente | E-mail/WhatsApp com texto only; log warning `das_delivery_no_pdf` |

### 6.3 Auditoria WhatsApp

- Registrar em `ChannelNotification` com `event_type`:
  - `guia_fiscal.available` (texto contador, se separado)
  - `guia_fiscal.available.pdf`
- Estender modelo ou usar `metadata` + `aggregate_type=guia_fiscal` até migration dedicada (decisão implementação).

### 6.4 Falhas

| Falha | Efeito |
|-------|--------|
| SMTP / e-mail | `DasEmailDeliveryError` → outbox FAILED → retry |
| Evolution mídia | `MediaDeliveryError` → outbox FAILED → retry |
| 8 falhas | Outbox `dead`; guia permanece `DISPONIVEL`; alerta ops manual |

---

## 7. Segurança e compliance

| Controle | Implementação |
|----------|---------------|
| Isolamento tenant | RLS + queryset scoped; cross-tenant → 404 |
| Sem link público | Anexo/stream autenticado apenas (ARD §11) |
| Dados sensíveis | PIX e linha digitável só para destinatários configurados |
| Logs | Mascarar PIX/telefone parcialmente em logs de aplicação |
| LGPD | Destinatário único registrado em settings; base B2B contratual |
| Permissão resend | `IsTenantWriter` / Hub role com escrita |
| Evolution | Número dedicado por tenant; disclaimer contratual de canal não oficial |

---

## 8. API e Hub (contrato v1)

### 8.1 API

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/v1/das/guias/{id}/resend-delivery/` | Enfileira reenvio; body `{ "channels": ["email","whatsapp"], "force": true, "delivery_email": "...", "delivery_phone": "..." }` |
| GET | `/api/v1/das/guias/{id}/pdf/` | **Existente** — download autenticado |

Emissão POST existente pode aceitar campos opcionais `delivery_email`, `delivery_phone` (override one-shot).

### 8.2 Hub V4

- **Preferências:** seção “Entrega DAS ao contador” (e-mail, WhatsApp, toggles `enabled`, `email_auto`, `whatsapp_auto`, `use_nfe_notify_email_for_das`)
- **Detalhe guia:** badges entrega e-mail/WhatsApp; botão “Reenviar ao contador”; link download PDF
- **Feedback reenvio:** toast “Reenvio enfileirado” (não síncrono)

---

## 9. Matriz de testes (contrato QA)

### 9.1 Obrigatórios (gate merge)

| ID | Caso |
|----|------|
| DAS-D06 | Fallback OFF + só `nfe_notify_email` → sem e-mail |
| DAS-D07 | Fallback ON → e-mail para `nfe_notify_email` |
| DAS-E01 | Happy path e-mail + PDF anexo |
| DAS-W01 | Happy path WhatsApp Evolution PDF + texto |
| DAS-W07 | Ops texto; contador PDF |
| DAS-W08 | Ops **não** recebe PDF |
| DAS-O02 | Falha delivery não altera `GuiaFiscal.status` |
| DAS-O05 | Reenvio API → outbox (202) |
| DAS-O03 | Idempotência retry outbox |
| DAS-E09 | DARF no assunto/caption |
| DAS-S02 | Cross-tenant resend → 404 |

### 9.2 Comando sugerido (pós-implementação)

```bash
python -m pytest apps/das/tests/test_das_delivery.py apps/das/tests/test_das.py -q
```

---

## 10. Fora de escopo (v1)

- Papel `accountant` e vínculo escritório ↔ tenant (RTC §9.3)
- Pacote ZIP por competência
- Lista CC / múltiplos e-mails ou números WhatsApp
- Grupo WhatsApp
- Webhook para ERP contábil
- Política de entrega **diferente** para DARF
- Obrigatoriedade Meta Cloud API (Evolution é decisão PO v1; migração Meta = ADR futuro)
- Templates HTML de e-mail (v1: texto plano + PDF)

---

## 11. Consequências

### Positivas

- Contador recebe guia no canal habitual (e-mail/WhatsApp) sem acesso ao Hub
- Reuso de outbox, storage e channel — baixo acoplamento, paridade RF-71/72
- Ops mantém visibilidade sem duplicar PDF no WhatsApp interno
- DAS/DARF unificados reduzem complexidade de suporte

### Negativas / riscos

- Evolution: risco de bloqueio de número (mitigação: número dedicado, migração Meta planejada)
- Feedback de reenvio não imediato (mitigação: badges + refresh na tela detalhe)
- Escritório com múltiplos destinatários precisa alias de e-mail (`fiscal@`) na v1

### Neutras

- Novos campos em `tenant.settings` (JSON, sem migration)
- Extensão de `metadata` em `GuiaFiscal` (JSON, sem migration)

---

## 12. Plano de implementação (referência)

| Ordem | Entrega |
|-------|---------|
| 1 | `apps/das/delivery.py` + testes unitários resolução destinatários |
| 2 | Estender `_notify_guia_available` + testes integração outbox |
| 3 | API `resend-delivery` + testes API |
| 4 | Hub preferências + detalhe (status, reenviar, download PDF) |
| 5 | Documentar settings em `.env.example` / manual PO |

Estimativa engenharia: **3–5 dias** (1 dev sênior), alinhado à análise vertical anterior.

---

## 13. Histórico

| Versão | Data | Autor | Notas |
|--------|------|-------|-------|
| 1.0.0 | 2026-09-08 | Engenharia EXEQ | Aprovado PO — decisões D-01…D-06 consolidadas |

---

## 14. Referências

- `apps/das/services.py` — `emitir_guia`, `_persist_guia_pdf`
- `apps/ops/dispatcher.py` — `_notify_guia_available`
- `apps/nfe/email_delivery.py` — RF-71
- `apps/channel/services.py` — `enqueue_media_notification`, RF-72
- `Docs/Exeq_Hub_ARD_WhatsApp_NFSe_Mensageria.md`
- `Docs/Exeq_Hub_v2_Platform_Architecture_Engineering_Guide.md` §7 Outbox
- `Docs/Exeq_Hub_v1_Business_Domain_Functional_Specification.md` — App `das`
