# DISCOVERY — Opção B — iFood + Emissão Fiscal Supervisionada no EXEQ Hub

| Campo | Valor |
|-------|-------|
| Status | **Análise concluída — aguardando decisão PO** |
| Data | 2026-09-01 |
| Solicitante | PO EXEQ |
| Executores | Consultoria sênior (Produto + Arquitetura + Fiscal + QA) |
| Escopo | **Análise e estimativa — sem implementação** |
| Referências | ADR-FOOD-001, ADR-NFE-001, auditoria codebase 2026-09-01 |

---

## Resumo executivo (1 página)

### Objetivo Opção B

Pedidos iFood centralizados no Hub **com emissão fiscal supervisionada em lote dentro do EXEQ** (operador seleciona → worker assíncrono → resultado SEFAZ). Estados logístico e fiscal **independentes**. Emissão **nunca** 100% automática.

### Situação atual

| Capacidade | Status |
|------------|--------|
| Ingestão iFood (pull/polling) | **Parcial** — stub/HTTP, beat 120s, idempotência pedido |
| Hub marketplace + pedidos | **Existe** |
| NFC-e modelo 65 | **Não existe** |
| NF-e modelo 55 B2B | **Existe** — `emit_invoice()` |
| Food ↔ NFe bridge | **Não existe** |
| Emissão lote marketplace | **Não existe** |
| Webhook iFood | **Não existe** |

**Conclusão:** repo está em **~Opção A**. Opção B exige slice vertical novo + decisão de emissor (parceiro ou build NFC-e).

### Recomendação consultiva

| Caminho | Recomendação |
|---------|--------------|
| **Go-to-market (< 6 meses)** | **Híbrida:** B1–B5 + B7–B11 + **B6 parceiro NFC-e** |
| **Ativo estratégico longo prazo** | Build NFC-e 65 em **fase 2** (após piloto com parceiro) |
| **Não recomendado** | Vender Opção B usando **só NF-e 55** como “cupom iFood” |

### Estimativa consolidada (faixa)

Premissa: 1–2 devs sênior + QA 40% dedicado; piloto 1 loja SP ~200 pedidos/dia.

| Trilha | Sprints (2 sem) | Dev (dias úteis) | QA (dias úteis) |
|--------|-----------------|------------------|-----------------|
| **B-parceiro** (NFC-e via API terceira) | **6–8** | **55–75** | **25–35** |
| **B-build** (NFC-e nativo EXEQ, fase 1) | **12–16** | **110–150** | **40–55** |
| Incremento build vs parceiro | **+6–8 sprints** | **+55–75** | **+15–20** |

Buffer recomendado: **+1 sprint** (integração iFood sandbox + homologação SEFAZ).

### Decisão PO necessária

1. Autorizar amend ADR-FOOD-001 (P2 → Opção B piloto)
2. Escolher **D1:** parceiro (recomendado fase 1) vs build
3. Assinar políticas D3–D6 (cancelamento, lote parcial, reemissão, reconciliação)
4. Autorizar épico **B1–B5 + B6-parceiro** ou no-go

---

## 1. Briefing PO (escopo)

### Dentro do escopo

- Ingestão iFood (estender polling + preparar webhook)
- `fiscal_status` separado de status logístico
- De-para `externalCode` → produto interno → dados fiscais (`NfeProduct`)
- Prontidão fiscal (reutilizar `build_validation()` / gate existente)
- Emissão manual em lote assíncrona
- Ignorar pedido com justificativa auditável
- Hub UI: listar, filtrar, selecionar, emitir, ignorar
- Multi-tenant, idempotência, concorrência
- Testes conforme matriz §4

### Fora do escopo

- Reescrever motor fiscal / segundo motor SEFAZ
- NFC-e 100% automática
- PDV, mesa, KDS, estoque WMS
- Substituir ERP completo
- OAuth iFood produção homologada (épico separado se não houver sandbox)

### Entregáveis desta discovery (concluídos)

- [x] Análise de impacto por épico
- [x] Estimativa dual (parceiro vs build)
- [x] Riscos e dependências
- [x] Proposta amend ADR
- [x] Matriz QA + plano de testes
- [x] Critérios de aceite

---

## 2. O que existe vs o que falta (auditoria 2026-09-01)

### Reutilizar sem reescrever

| Componente | Path |
|------------|------|
| `FoodOrder` + idempotência | `apps/food/models.py`, `operations.py` |
| `import_marketplace_order` | `apps/food/operations.py:342+` |
| Normalize iFood | `integrations/marketplace/normalize.py` |
| Gateway stub/HTTP | `integrations/marketplace/factory.py` |
| Celery beat sync | `apps/food/tasks.py`, `config/settings.py` |
| `emit_invoice()` | `apps/nfe/services.py:484+` |
| `build_validation()` | `apps/nfe/tax.py` |
| Gate emitente | `apps/nfe/gate.py` |
| Polling/reconcile NFe | `apps/nfe/tasks.py`, `reconciliation.py` |
| Hub patterns Food | `apps/food/hub_views.py` |
| Tenant isolation | `TenantOwnedModel`, JWT/Hub auth |
| Webhook pattern (ref.) | `apps/food/webhook_views.py` (Mercado Pago) |

### Criar (gap Opção B)

| Gap | Épico |
|-----|-------|
| `fiscal_status`, FK nota, ignore audit | B2 |
| `FoodProduct.nfe_product` ou map dedicado | B3 |
| Readiness por pedido | B4 |
| Batch emit API + Celery task | B5 |
| Adapter `FoodOrder → NfeInvoice` | B5 |
| Emissor NFC-e (parceiro ou mod 65) | B6 |
| Hub fiscal iFood | B8 |
| `FoodMarketplaceEvent` (idempotência evento) | B1 |
| Testes Food→fiscal | B11 |

### Alterar (mínimo)

| Arquivo | Alteração |
|---------|-----------|
| `apps/food/models.py` | Campos fiscais |
| `apps/food/operations.py` | Pós-import readiness; update logístico |
| `apps/food/serializers.py`, `views.py` | API fiscal |
| `apps/nfe/models.py` | FK opcional `source_food_order` |
| `integrations/marketplace/normalize.py` | Status iFood, externalCode |
| `apps/hub_v4/urls.py` + templates | UI fiscal |

### Não alterar (core)

- `integrations/sefaz_nfe/` (mod 55) — salvo extensão explícita mod 65
- `apps/issuance/` (NFS-e)
- `apps/fiscal/` (ISS)

---

## 3. Épicos B1–B11 — análise e estimativa

### B1 — Ingestão iFood

**Escopo:** evento bruto, idempotência, ACK, sync status logístico, webhook prep.

| Item | Detalhe |
|------|---------|
| Existe | Polling, import idempotente, normalize |
| Falta | `FoodMarketplaceEvent`, webhook endpoint, ACK policy, update cancelamento |
| Riscos | API iFood real (OAuth); ordem de eventos |
| Dev | 6–10 dias |
| QA | 4–5 dias |

### B2 — Estados + API

**Escopo:** `fiscal_status`, API list/detail/filters, separação logístico/fiscal.

| Dev | 4–6 dias | QA | 3–4 dias |

### B3 — De-para produto

**Escopo:** FK `FoodProduct → NfeProduct`, UI map, `externalCode` via normalize + settings.

| Dev | 5–8 dias | QA | 4–5 dias |

### B4 — Prontidão fiscal

**Escopo:** wrapper `assess_food_order_fiscal_readiness()` → `build_validation()`; READY/PENDING/INVALID.

| Dev | 5–8 dias | QA | 4–5 dias |

### B5 — Emissão lote + worker

**Escopo:** `POST emit-batch`, Celery, locks, `PROCESSING→AUTHORIZED|REJECTED`, adapter draft.

| Dev | 10–15 dias | QA | 6–8 dias |

**Cenários críticos:** EX-EMT-03 a 07 (concorrência, timeout SEFAZ).

### B6a — Emissor parceiro NFC-e

**Escopo:** port `FiscalEmissionPort`, integração API (Focus/Nuvem Fiscal/eNotas/etc.), mapper resposta.

| Dev | 12–18 dias | QA | 5–7 dias |
| Dependência | Contrato parceiro, sandbox, pricing |

### B6b — Build NFC-e 65 nativo

**Escopo:** mod 65 XML, CSC, dest consumidor, DANFE NFC-e, contingência básica 1 UF.

| Dev | 50–70 dias | QA | 15–20 dias |
| Dependência | ADR-NFE-002, certificação SEFAZ SP |

### B7 — Ignorar pedido

| Dev | 2–4 dias | QA | 2–3 dias |

### B8 — Hub UI fiscal

| Dev | 8–12 dias | QA | 4–6 dias |

### B9 — Segurança

| Dev | 3–5 dias | QA | 2–3 dias |

### B10 — Logs / observabilidade

| Dev | 2–3 dias | QA | 1–2 dias |

### B11 — QA automatizado

| QA acumulado | 25–35 dias (parceiro) / 40–55 (build) |

---

## 4. Matriz de cenários QA (fonte da verdade)

### Happy path

| ID | Cenário | Prioridade |
|----|---------|------------|
| HP-01 | Pedido iFood novo → PENDING fiscal | P0 |
| HP-02 | Mapeamento produto → READY | P0 |
| HP-03 | Emitir 1 pedido READY → AUTHORIZED | P0 |
| HP-04 | Emitir N pedidos READY → todos processados | P0 |
| HP-05 | REJECTED exibe motivo SEFAZ | P0 |
| HP-06 | Ignorar com justificativa → IGNORED_BY_USER | P1 |
| HP-07 | Evento logístico DELIVERED não altera fiscal | P1 |

### Ingestão (EX-ING)

| ID | Cenário | Prioridade |
|----|---------|------------|
| EX-ING-01 | Evento duplicado | P0 |
| EX-ING-02 | Pedido duplicado (external_order_id) | P0 |
| EX-ING-03 | Payload inválido | P1 |
| EX-ING-04 | Tenant/merchant desconhecido | P0 |
| EX-ING-05 | Conexão inativa | P1 |
| EX-ING-06 | Eventos fora de ordem | P1 |
| EX-ING-07 | Cancelamento iFood pré-emissão | P0 |
| EX-ING-08 | Cancelamento pós-AUTHORIZED | P0 |
| EX-ING-09 | Retry async pós-ACK | P1 |
| EX-ING-10 | Item sem externalCode | P1 |

### De-para (EX-MAP)

| ID | Cenário | Prioridade |
|----|---------|------------|
| EX-MAP-01 | externalCode mapeado + fiscal OK | P0 |
| EX-MAP-02 | Sem mapeamento | P0 |
| EX-MAP-03 | Produto inativo | P1 |
| EX-MAP-04 | Sem NfeProduct | P0 |
| EX-MAP-05 | Fiscal incompleto (NCM/CFOP) | P0 |
| EX-MAP-06 | Preço/qtd do pedido prevalece | P1 |
| EX-MAP-08 | Alterar map recalcula PENDING | P1 |

### Prontidão (EX-RDY)

| ID | Cenário | Prioridade |
|----|---------|------------|
| EX-RDY-01 | Cancelado → não elegível | P0 |
| EX-RDY-02 | IGNORED → não elegível | P0 |
| EX-RDY-03 | AUTHORIZED → não elegível | P0 |
| EX-RDY-04 | PROCESSING → não elegível | P0 |
| EX-RDY-05 | Emitente sem gate | P0 |

### Emissão lote (EX-EMT)

| ID | Cenário | Prioridade |
|----|---------|------------|
| EX-EMT-01 | Lote vazio → 400 | P1 |
| EX-EMT-02 | Mix elegível/inelegível (política PO) | P1 |
| EX-EMT-03 | Duplo clique emitir | P0 |
| EX-EMT-04 | Dois usuários mesmo pedido | P0 |
| EX-EMT-05 | Worker morre em PROCESSING | P0 |
| EX-EMT-06 | SEFAZ rejeita | P0 |
| EX-EMT-07 | Timeout SEFAZ, nota autorizada | P0 |
| EX-EMT-08 | Timeout SEFAZ, não autorizada | P1 |
| EX-EMT-09 | Parceiro indisponível | P1 |
| EX-EMT-10 | Pedido outro tenant | P0 |
| EX-EMT-11 | Reemissão após REJECTED | P1 |
| EX-EMT-12 | Valor zero / desconto total | P2 |

### Ignorar (EX-IGN)

| ID | Cenário | Prioridade |
|----|---------|------------|
| EX-IGN-01 | Justificativa vazia | P1 |
| EX-IGN-03 | Ignorar AUTHORIZED → 409 | P0 |
| EX-IGN-04 | Ignorar PROCESSING → 409 | P0 |
| EX-IGN-05 | Auditoria completa | P1 |

### Segurança (EX-SEC)

| ID | Cenário | Prioridade |
|----|---------|------------|
| EX-SEC-01 | Cross-tenant | P0 |
| EX-SEC-02 | Worker tenant errado | P0 |
| EX-SEC-03 | Webhook sem auth | P0 |
| EX-SEC-04 | Token não em log | P0 |
| EX-SEC-05 | Read-only emite → 403 | P1 |

### Plano de testes por camada

| Camada | Cobertura |
|--------|-----------|
| Unit | readiness, idempotência import, lock batch, normalize |
| Integration | emit-batch → stub parceiro/SEFAZ, cross-tenant |
| Hub manual | filtros, seleção, ignore, mensagens erro |
| E2E piloto | 1 tenant, 3 produtos, 5 pedidos stub iFood |

**Gate release:** zero P0 aberto.

---

## 5. Decisões PO (D1–D8)

| ID | Decisão | Opções | Recomendação consultoria |
|----|---------|--------|--------------------------|
| D1 | Emissor fase 1 | Parceiro / Build / Híbrida | **Parceiro** |
| D2 | Ingestão fase 1 | Polling / Webhook+poll | **Polling + webhook prep** |
| D3 | Cancel iFood pré-emissão | INVALID / bloqueio emit | **INVALID** (não elegível) |
| D4 | Reemitir após REJECTED | Sim / Não | **Sim** (manual, 1 nota por pedido) |
| D5 | Lote parcial | Só elegíveis / tudo-ou-nada | **Só elegíveis + relatório** |
| D6 | Reconcile PROCESSING | TTL 15 min | **15 min → consulta emissor** |
| D7 | Piloto UF | SP only | **SP only** |
| D8 | RBAC emitir | tenant_admin + food_operator | **food_operator+** |

**PO provisório (discovery):** D1 parceiro fase 1; piloto 1 loja SP ~200 pedidos/dia.

---

## 6. Critérios de aceite (DoD Opção B)

- [ ] Pedido iFood persiste; `fiscal_status=PENDING` inicial
- [ ] Status logístico e fiscal independentes
- [ ] Idempotência evento + pedido (constraints DB)
- [ ] De-para e prontidão visíveis API + Hub
- [ ] Lote assíncrono: PROCESSING → AUTHORIZED | REJECTED
- [ ] Zero emissão duplicada (EX-EMT-03, 04, 07)
- [ ] Ignorar exige justificativa + auditoria
- [ ] Cross-tenant bloqueado
- [ ] P0 QA executado com evidência
- [ ] Logs: tenant, pedido, tentativa — sem secrets

---

## 7. Riscos e dependências

| Risco | Gravidade | Mitigação |
|-------|-----------|-----------|
| NFC-e inexistente | Alta | Parceiro fase 1 |
| NF-e 55 ≠ cupom B2C | Alta | Não vender como NFC-e |
| iFood OAuth não pronto | Média | Stub/sandbox piloto |
| Duplicidade emissão | Alta | Lock + unique source_food_order |
| Timeout SEFAZ | Alta | Reconcile existente + consulta parceiro |
| Margem parceiro | Média | Pricing por pacote notas |
| ADR P2 conflito | Média | Amend §8 abaixo |
| RTC 2026 NFC-e | Média | Monitorar; parceiro absorve curto prazo |

**Dependências externas:** sandbox iFood, contrato emissor NFC-e, certificado A1 tenant piloto.

---

## 8. Proposta amend ADR-FOOD-001

**Texto sugerido (§2 tabela + §4 linha nova):**

> Emissão fiscal Food marketplace (iFood) — **P2.1 piloto autorizado**  
> Escopo piloto: ingestão existente + fiscal_status + prontidão + emissão supervisionada em lote via **emissor parceiro NFC-e**; 1 UF (SP); manual; sem auto 100%.  
> NFC-e nativa EXEQ: **P2.2** pós-piloto.  
> NF-e 55 **não** substitui NFC-e no escopo iFood B2C.

PO assina amend antes de Sprint 1 Opção B.

---

## 9. Ordem de implementação sugerida

| Sprint | Entrega |
|--------|---------|
| S1 | B2 models/migration + B3 de-para + testes unit |
| S2 | B1 eventos + B4 readiness + API list/filters |
| S3 | B5 batch backend + worker + idempotência emissão |
| S4 | B6 parceiro integração + stub homolog |
| S5 | B8 Hub UI + B7 ignore |
| S6 | B9–B11 hardening + QA P0 + piloto |
| S7 | Buffer iFood sandbox + ajustes produção |
| S8+ | B6b NFC-e nativo (se PO autorizar P2.2) |

---

## 10. Análise consultiva por lente

### Produto

- Dor real; EXEQ diferencia em **multi-tenant + fiscal supervisionado + base NFS-e**.
- Opção B vendável **com parceiro**; build nativo é investimento estratégico.
- Não competir com PDV no curto prazo.

### Arquitetura

- Estender Food + adapter fino para emissor; **não** duplicar `emit_invoice` core.
- Port `FiscalEmissionPort` permite trocar parceiro → nativo.
- Reutilizar Celery, reconcile, gate patterns.

### Fiscal / SEFAZ

- Cancelamento pós-emissão = fluxo cancelamento NFC-e (fora lote).
- CPF consumidor: validar requisito parceiro vs pedido iFood (pode ser opcional NFC-e).
- Contingência: parceiro fase 1; nativo fase 2.

### QA sênior

- Maior densidade de bugs: **B5 concorrência**, **B6 mapping erro parceiro**, **EX-ING-07/08 cancelamento**.
- Automatizar P0 antes de piloto produção.
- Fixture tenant `food-qa` existente — estender.

---

## 11. Tabela estimativa por épico (consolidada)

| Épico | Dev (dias) | QA (dias) | Risco |
|-------|------------|-----------|-------|
| B1 Ingestão | 6–10 | 4–5 | Médio |
| B2 Estados/API | 4–6 | 3–4 | Baixo |
| B3 De-para | 5–8 | 4–5 | Médio |
| B4 Prontidão | 5–8 | 4–5 | Médio |
| B5 Lote/worker | 10–15 | 6–8 | **Alto** |
| B6a Parceiro | 12–18 | 5–7 | **Alto** |
| B6b Build NFC-e | 50–70 | 15–20 | **Crítico** |
| B7 Ignore | 2–4 | 2–3 | Baixo |
| B8 Hub UI | 8–12 | 4–6 | Médio |
| B9–B10 | 5–8 | 3–5 | Baixo |
| **Total B-parceiro** | **55–75** | **25–35** | |
| **Total B-build** | **110–150** | **40–55** | |

---

## 12. Próximo passo PO

1. [ ] Revisar este documento  
2. [ ] Decidir **Go / Go faseado / No-go**  
3. [ ] Assinar D1–D8  
4. [ ] Aprovar amend ADR-FOOD-001 §8  
5. [ ] Autorizar Sprint S1 (B2+B3) — **somente após Go**

---

*Documento gerado por discovery executado em 2026-09-01. Nenhum código alterado.*
