# EXEQ Hub — LLR: Domínio NF-e SEFAZ (greenfield) + emissor próprio modelo 55

| Campo | Valor |
|-------|--------|
| Tipo | **Requisitos de baixo nível (LLR) de domínio e integração** — sem implementação neste documento |
| Status | **Fábrica autorizada PO 2026-08-05** — v0.1.x; iniciar U1/U2 (stub); G-EMIT-NFE real depende IE+credenciamento SP |
| Data | 2026-08-05 |
| Público | Engenharia backend, Tech Lead, QA, fiscal, ops |
| Escopo MVP | NF-e **55** B2B saída; **SEFAZ próprio**; SN + Normal (ondas); **UF pivot SP**; até **10 UFs** no multi; **sem estoque** |
| Premissa | **Greenfield** — zero NF-e produto em banco; sem migração de notas produto; sem multa retroativa de produto *hoje* |
| ADR | `Docs/ADR_NFE_001_Emissor_Proprio_SEFAZ.md` |
| UI | `Docs/Exeq_Hub_LLR_NFe_UI_B2B_Sem_Estoque.md` v0.2 |
| Impacto | `Docs/Exeq_Hub_NFe_Reanalise_Impacto_NFSe_Homologada.md` v1.0 |
| Irmão | LLR NFS-e 0.3 — **padrão de LLR e de plataforma**; **não** copiar DPS/ISS |
| Código | **Não implementa** neste documento |

---

## 0. Decisões de domínio travadas

| ID | Decisão | Valor |
|----|---------|--------|
| D-01 | Destino | Emissor **próprio EXEQ** SEFAZ (modelo 55) |
| D-02 | Agregador | **Não** default; lab opcional via `NfeProvider` kind explícito |
| D-03 | Greenfield | Models/API NF-e novos; **sem** alterar notas produto inexistentes |
| D-04 | Isolamento NFS-e | Tabelas/fluxo SEFIN **intactos**; module boundary; `NFE_ENABLED` |
| D-05 | Cert | **A1 only**; **mesmo** `DigitalCertificate` / PFX da emissão NFS-e do prestador (CNPJ alinhado) |
| D-05a | Emitente | **Mesmo** `Provider` (CNPJ) já usado na NFS-e; gate reusa resolução primary por `(tenant, cnpj)` |
| D-06 | Numeração | Hub **reserva/consome** nNF por company+série+tpAmb |
| D-07 | Snapshot | Imutável a partir do submit bem-sucedido para path de autorização |
| D-08 | Hard delete | Autorizada/cancelada **nunca** apagadas |
| D-09 | Poll | Happy path sync se SEFAZ permitir; senão polling reconciliação; teto → `failed` |
| D-10 | PDF | DANFE EXEQ; falha PDF ≠ desfaz `authorized` |
| D-11 | Motor | Mercadoria separado de ISS; `taxes` map extensível (RTC) |
| D-12 | UFs | **UF pivot = SP (São Paulo)**; onda 2 ≤ 10 UFs (lista a fechar; não bloqueia G-EMIT-NFE SP) |
| D-13 | Fiscal MVP | SN CSOSN básico + Normal CST 00 interno; interestadual simples em onda 1.b; **ST fora** onda 1 |
| D-14 | Porta | `NfeProvider`: `emitir`, `consultar`, `cancelar` (+ `inutilizar` futuro) |
| D-15 | Camadas | View → Serializer → App Service → Domain → ORM; HTTP só em `integrations/sefaz_nfe` |

---

## 1. Pacote de estudo oficial (U0 — antes do spike)

O time deve baixar/consultar (versão **vigente** na data do spike):

| # | Fonte | Uso |
|---|--------|-----|
| S-01 | Manual de orientação contribuinte NF-e 4.00 | Fluxo autorizar/consultar/cancelar |
| S-02 | XSD / pacote schemas NF-e | Validação local pré-envio |
| S-03 | NTs vigentes (PL, rejeições, QT) | Layout e cStat |
| S-04 | Endpoints webservice por UF (prod + homolog) | `SefazEndpointCatalog` |
| S-05 | Regras de contingência (referência futura) | Roadmap pós G-EMIT-NFE 1 UF |

Checklist U0:

- [x] **UF pivot = SP (São Paulo)** — decisão PO 2026-08-05  
- [x] **CNPJ + cert A1** = os **já existentes** no Hub para NFS-e (`Provider` + `DigitalCertificate` primary / ativo) — decisão PO 2026-08-05  
- [ ] Confirmar no lab: CNPJ do prestador tem **IE-SP** (ou regra isento válida) e está apto a NF-e homolog SEFAZ-SP (**cadastro SEFAZ**, não novo cert no Hub)  
- [ ] Lista das **9 UFs restantes** (total 10 no go-live multi) — **não bloqueia** G-SPIKE/G-EMIT SP  
- [ ] Paths webservice **SEFAZ-SP** (prod + homolog NFe 4.00) no catálogo interno  
- [ ] Amostra códigos rejeição (cStat) priorizados no QA  

**Identidade lab (reuso NFS-e):** não provisionar segundo certificado “NF-e only”. Worker SEFAZ carrega o **mesmo** material PFX/senha que o path SEFIN (`DigitalCertificate` + `TenantSecret`), com CNPJ do `Provider` emitente.

**Referência SP (confirmar no manual vigente no spike — não hardcodar path sem checar NT):**  
emissor SP costuma usar webservice próprio SEFAZ-SP (não SVRS). Homologação e produção têm bases distintas; catalogar em `SefazEndpoint` no U2/U3.

Docs internos EXEQ: ADR-NFE-001, reanálise impacto, LLR UI, ADR-NFSE-001 (só reuso de *padrão*).

---

## 2. Atores e sistemas

| Ator | Responsabilidade |
|------|------------------|
| **EXEQ Hub** | Draft, tax, número, snapshot, XML, XMLDSig, adapter SEFAZ, FSM, artefatos, outbox |
| **SEFAZ (UF)** | Autorização / rejeição / denegação / protocolo |
| **Emitente (Provider)** | CNPJ, IE, CRT, endereço, cert A1, série |
| **Destinatário (Customer)** | Doc, IE, endereço, indIEDest |
| **Operador** | UI/API cria e transmite |
| **NFS-e path** | Independente; não consumido por este fluxo |

---

## 3. Modelo de domínio (greenfield)

### 3.1 Aggregates e entidades (Must no DER amend)

| Nome sugerido | Tipo | Responsabilidade |
|---------------|------|------------------|
| **NfeNumberSeries** | AR | `serie`, `next_number`, `tp_amb`, lock; unique (tenant, company, serie, tp_amb) |
| **NfeNumberReservation** | entity | reserved / consumed / void; liga draft/invoice |
| **NfeProduct** | AR master | SKU fiscal **sem estoque** (NCM, CFOP defaults, CST/CSOSN, PIS/COFINS…) |
| **NfeDraft** | AR | Editável; `idempotency_key`; `version` optimistic lock |
| **NfeDraftItem** | entity | Linhas editáveis |
| **NfeInvoice** | AR | Documento pós-submit; imutável se authorized/cancelled |
| **NfeInvoiceItem** | entity | **Cópia** dos dados fiscais do item |
| **NfeFiscalSnapshot** | VO/JSON 1:1 | Partes + taxes + engine_version + layout_version + catalog_version |
| **NfeTransmissionAttempt** | entity | raw redacted, HTTP, cStat |
| **NfeDomainEvent** | entity | timeline (from→to, actor, metadata, correlation) |
| **NfeArtifact** | entity | kind: `xml_authorized`, `xml_cancel`, `danfe_pdf`, … + checksum |
| **NfeCancellation** | entity | justificativa, protocolo evento |
| **SefazEndpoint** | config | UF, ambiente, URL, notes |
| **NfeCompanyConfig** | entity/settings | série default, email auto, feature |

**Reuso:** `Tenant`, `Provider` (company), `Customer`, `DigitalCertificate`, `StoredFile`, membership — **sem** acoplar a `NfIssue` de serviço.

### 3.2 O que **não** usar

- `ServiceCatalogItem` como produto  
- `MunicipalTaxRule` / ISS para ICMS  
- `integrations/nfse` para HTTP SEFAZ  
- Mesma linha ORM de `NfIssue` para item mercadoria  

---

## 4. Máquina de estados (FSM)

### 4.1 Estados

| Estado | Significado |
|--------|-------------|
| `draft` | Editável |
| `queued` | Aceito emit; espera worker |
| `number_reserved` | nNF reservado (pode ser subestado/flag em queued) |
| `submitting` | Em chamada SEFAZ |
| `polling` | Aguardando recibo/protocolo (reconciliação) |
| `authorized` | Protocolo OK; chave definida |
| `rejected` | Rejeição fiscal SEFAZ/cStat |
| `failed` | Infra/timeout esgotado / erro local grave |
| `cancel_requested` | Evento cancel enviado/pendente |
| `cancelled` | Cancelamento autorizado |

### 4.2 Transições principais

```text
draft --validate (side-effect free)--> draft (+ last_validation)
draft --emit--> number_reserved --> queued --> submitting
submitting --sync OK--> authorized
submitting --timeout/5xx/ambiguous--> polling
polling --OK--> authorized | rejected
polling --exhausted--> failed
submitting --cStat reject--> rejected
authorized --cancel--> cancel_requested --> cancelled | authorized (negado)
draft --discard--> (delete soft / hard only draft)
```

### 4.3 Regras

| ID | Regra |
|----|--------|
| FSM-01 | `authorized` / `cancelled` **imutáveis** no payload fiscal |
| FSM-02 | Um único writer de transição por invoice (lock de linha) |
| FSM-03 | Idempotência de promoção a `authorized` (sem double artifact/outbox) |
| FSM-04 | `allowed_actions` derivado só no servidor |
| FSM-05 | Poll teto → `failed` + alerta ops (não infinito) |

### 4.4 Numeração (D-06)

| Momento | Ação |
|---------|------|
| **Reserve** | No `emit`, após gate+validate OK, **antes** de montar XML final com nNF |
| **Consume** | Em `authorized` **ou** quando SEFAZ confirma uso do nNF mesmo em certos erros |
| **Void** | Abort **antes** de qualquer envio SEFAZ bem-sucedido; se já enviou, **não** liberar nNF — gap/inutilização (fase 2) |
| **Concorrência** | Lock por `(company, serie, tp_amb)`; UNIQUE físico no número consumido |
| **Ambiente** | Homolog e produção **séries/contadores separados** |

### 4.5 Reprocesso

| Caso | Ação |
|------|------|
| `rejected` / `failed` e número **não** consumido | Reabrir `draft` mesmo id ou re-emit após edit |
| Número consumido / `clone_required` | Nova nota (clone dados); nNF novo |
| `authorized` | Só cancel (janela) ou CCe (fora MVP) |

---

## 5. Requisitos funcionais

### 5.1 Gates e pré-condições

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-01 | Emit só se `NFE_ENABLED` e company (`Provider`) com IE (ou isento válido), CRT, endereço+IBGE, série ativa, tpAmb definido, e **cert A1** resolvido como no NFS-e: preferir `DigitalCertificate` **primary** do CNPJ do prestador (mesmo registro usado no SEFIN); status active/expiring, `not_after` futuro, `cert_type=a1` | Must |
| RF-01a | **Proibido** exigir upload/segundo PFX “só NF-e” se já existe primary válido para o CNPJ no tenant | Must |
| RF-01b | CNPJ do XML emitente = CNPJ do Provider = CNPJ do certificado (mesmo gate de alinhamento da NFS-e) | Must |
| RF-02 | Destinatário com doc, nome, endereço completo+IBGE; IE se indIEDest=1 | Must |
| RF-03 | ≥1 item com NCM, CFOP, qtd>0, valores, origem, CSOSN **ou** CST, PIS/COFINS | Must |
| RF-04 | Pagamento tPag com valor ≈ total da nota (tolerância centavos definida) | Must |
| RF-05 | CFOP coerente com UF emit × UF dest (regra motor/validator) | Must |
| RF-06 | `idempotency_key` única por tenant | Must |

### 5.2 Draft e concorrência

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-10 | CRUD draft com `version` / optimistic lock → HTTP 409 | Must |
| RF-11 | Dois editores: last-write-wins **proibido** sem version | Must |
| RF-12 | Validate **não** muda status para authorized; devolve errors + totals + tax result | Must |

### 5.3 Motor fiscal (mercadoria)

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-20 | `TaxEngineGoods.resolve(draft|snapshot_input)` puro e testável | Must |
| RF-21 | Separar: rule catalog versionado · calculator · validator · override (role) | Must |
| RF-22 | Onda 1a: SN CSOSN (ex. 102/400) + Normal CST 00 interno | Must |
| RF-23 | Onda 1b: interestadual simples (alíquotas padrão) | Should |
| RF-24 | ST / monofásico / combustível | Won’t MVP |
| RF-25 | Resultado em `taxes` **map extensível** (chaves `icms`, `pis`, `cofins`, futuro `ibs`/`cbs`) | Must |
| RF-26 | Override manual grava flag + user no snapshot | Must |
| RF-27 | `tax_engine_version` + `catalog_version` no snapshot | Must |

### 5.4 Snapshot

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-30 | No emit: copiar emitente, dest, itens, totais, taxes, versões | Must |
| RF-31 | Product/Customer FK opcionais; **não** fontes de verdade pós-authorize | Must |
| RF-32 | `payload_hash` canônico do snapshot | Must |
| RF-33 | Update de NfeProduct **não** altera Invoice authorized | Must |
| RF-34 | Greenfield: sem backfill; regra vale desde a 1ª nota | Must |

### 5.5 XML e transmissão

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-40 | Builder XML a partir do snapshot — **não** na View | Must |
| RF-41 | Validação XSD local antes do POST; falha → `failed`/`rejected` pre-tx **sem** HTTP | Must |
| RF-42 | XMLDSig A1 com o **mesmo** material PFX do `DigitalCertificate` reutilizado; testes fixture assinatura inválida falham suite | Must |
| RF-43 | `SefazNfeProvider` implements port; router por UF emitente + tpAmb | Must |
| RF-44 | Persistir attempt (request/response redacted) | Must |
| RF-45 | Map cStat/status → FSM | Must |
| RF-46 | Reconciliação se worker cai pós-envio (consultar por recibo/chave) | Must |

### 5.6 Cancelamento

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-50 | Só `authorized`; justificativa 15–255 | Must |
| RF-51 | Evento SEFAZ; sucesso → `cancelled` | Must |
| RF-52 | Regenerar DANFE cancelada (marca) | Must |
| RF-53 | Cancel negado: permanece authorized + erro | Must |

### 5.7 Artefatos

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-60 | XML autorizado persistido + checksum | Must |
| RF-61 | DANFE gerado do XML (layout versionado `danfe_layout_version`) | Must |
| RF-62 | Idempotência por (invoice, kind, layout_version) | Must |
| RF-63 | Download API com auth multi-tenant (+ signed URL Should) | Must |
| RF-64 | EX-PDF: authorized com PDF pendente + retry job | Must |

### 5.8 Outbox e eventos de integração

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-70 | Eventos: `nfe.authorized`, `nfe.cancelled`, `nfe.rejected` (versionados) | Must |
| RF-71 | E-mail XML+DANFE via outbox; falha e-mail ≠ desfaz authorize | Must |
| RF-72 | WhatsApp mídia só se canal ligar a `nfe.authorized` (fora MVP se não pedido) | Could |

### 5.9 Multi-tenant e segurança

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-80 | Todo query por tenant; invoice/company isolation | Must |
| RF-81 | Cert bound a company/CNPJ do emitente | Must |
| RF-82 | Sem log de senha PFX | Must |
| RF-83 | Admin/prod switch auditável | Must |
| RF-84 | Rate limit emit/cancel | Should |

### 5.10 Observabilidade

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-90 | `correlation_id` por emissão; propagar worker | Must |
| RF-91 | Métricas: authorize rate, reject by cStat, queue lag, cert expiry | Should |
| RF-92 | Alerta poll exhausted + cert < 30d | Should |

### 5.11 Tabelas fiscais / catálogos

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-100 | NCM/CFOP/IBGE e regras com **versão published/superseded** | Must |
| RF-101 | Import com auditoria who/when/hash; rollback = republish prev | Should |
| RF-102 | Snapshot grava versões usadas | Must |

### 5.12 Lab agregador (opcional)

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-LAB-01 | Kind `focus` (ou similar) só se settings/tenant override lab | Won’t prod |
| RF-LAB-02 | Domain canônico **não** vaza campos só-vendor | Must if lab |

### 5.13 Não regredir NFS-e

| ID | Requisito | Pri |
|----|-----------|-----|
| RF-NFSE-01 | PR NF-e não altera mappers DPS/SEFIN default | Must |
| RF-NFSE-02 | Smoke NFS-e no CI ou checklist release (G-IMPACT-OK) | Must |

---

## 6. Fluxos principais

### 6.1 Emit happy path

```text
create draft → patch items → validate (TaxEngineGoods)
  → emit (Idempotency-Key)
       → gates RF-01..06
       → reserve number
       → freeze snapshot + hash
       → queue worker
  → build XML + XSD + sign
  → SefazAdapter.emit
  → authorized → store xml + protocol + key
  → artifacts DANFE
  → outbox nfe.authorized
```

### 6.2 Rejeição

```text
SEFAZ cStat reject → rejected + message
  → se number not consumed → allow edit
  → se consumed → clone_required
```

### 6.3 Cancel

```text
authorized + justificativa → cancel event → cancelled → DANFE cancelada
```

### 6.4 Recuperação

```text
timeout após POST → polling/consultar
  → promote authorized idempotente
  → ou failed após teto
```

---

## 7. Fluxos de exceção (EX-*)

### 7.1 Pré-envio

| ID | Cenário | Comportamento |
|----|---------|---------------|
| EX-PRE-01 | Cert ausente/expirado (**mesma** resolução da NFS-e) | Bloqueia emit |
| EX-PRE-01b | CNPJ cert ≠ CNPJ Provider | Bloqueia emit |
| EX-PRE-02 | Série/número lock fail | 409/retry |
| EX-PRE-03 | Validate tax fail | 422; permanece draft |
| EX-PRE-04 | XSD inválido | failed pre-tx; sem HTTP |
| EX-PRE-05 | Feature flag off | 403 negócio |
| EX-PRE-06 | CFOP × UF inválido | 422 |

### 7.2 Transporte SEFAZ

| ID | Cenário | Comportamento |
|----|---------|---------------|
| EX-NET-01 | Timeout | polling / retry limitado |
| EX-NET-02 | 5xx SEFAZ | retry + backoff; depois failed |
| EX-NET-03 | 4xx auth/cert | failed; sem martelar |
| EX-NET-04 | Resposta ilegível | failed + raw |

### 7.3 Negócio autoridade

| ID | Cenário | Comportamento |
|----|---------|---------------|
| EX-FIS-01 | Rejeição cStat | rejected + código |
| EX-FIS-02 | Denegada (se aplicável) | estado terminal distinto ou rejected tipado |
| EX-FIS-03 | Autorização após timeout local | consulta promove authorized |
| EX-FIS-04 | Cancel recusado | authorized + erro |

### 7.4 Poll / concorrência

| ID | Cenário | Comportamento |
|----|---------|---------------|
| EX-POL-01 | Poll esgota | failed + alerta |
| EX-POL-02 | Double finalize | uma transição; sem double outbox |
| EX-CON-01 | Dois emit mesmo draft | 409 / uma reserva |

### 7.5 Artefatos / segurança

| ID | Cenário | Comportamento |
|----|---------|---------------|
| EX-PDF-01 | PDF fail | authorized; retry PDF |
| EX-XML-01 | XML ausente | retry consulta; não inventar |
| EX-SEC-01 | Tenant A → invoice B | 403/404 |
| EX-SEC-02 | Cert empresa B em emit A | proibido |

### 7.6 NFS-e

| ID | Cenário | Comportamento |
|----|---------|---------------|
| EX-NFSE-01 | Regressão SEFIN em PR NF-e | bloqueia merge / smoke fail |

---

## 8. Contrato API (esboço Must — detalhar OpenAPI U0)

| Op | Path | Notas |
|----|------|-------|
| GET | `/api/v1/nfe/gate/` | T0 |
| GET/PUT | `/api/v1/nfe/config/` | série, amb, flags |
| CRUD | `/api/v1/nfe/products/` | T4 |
| POST/PATCH | `/api/v1/nfe/drafts/` | version |
| POST | `.../validate/` | 200 + errors |
| POST | `.../emit/` | 202; Idempotency-Key |
| GET | `/api/v1/nfe/invoices/` | cursor, filtros |
| GET | `/api/v1/nfe/invoices/{id}/` | + allowed_actions |
| GET | `.../events/` | timeline |
| POST | `.../cancel/` | Idempotency-Key |
| GET | `.../artifacts/{kind}/` | authz |
| POST | `.../resend-email/` | outbox |

Erros: `{ code, message, field_errors[] }`.  
Versionamento: prefixo `/api/v1/`.

---

## 9. Arquitetura de runtime

```text
UI / API
  → NfeApplicationService
       → Domain (Draft/Invoice/NumberSeries)
       → TaxEngineGoods
       → (emit) Outbox/Queue NfeEmitJob
Worker
  → XmlBuilder → XsdValidator → Signer(A1)
  → NfeProvider/sefaz  → UF router
  → FSM transition
  → ArtifactService (XML, DANFE)
  → Outbox domain events
```

Camadas alinhadas ao plano NFS-e §4.1 — **pacotes distintos**.

---

## 10. Requisitos não funcionais

| ID | Requisito |
|----|-----------|
| RNF-01 | Nenhum HTTP SEFAZ fora de `integrations/` |
| RNF-02 | Testes unitários: tax, FSM, número, snapshot, mapper, status map na mesma entrega da regra |
| RNF-03 | Spike 1 UF antes de multi-UF |
| RNF-04 | Secrets cert só storage seguro |
| RNF-05 | API emit retorna rápido; worker faz SEFAZ |
| RNF-06 | Solução enxuta; sem Onion/CQRS total; DER amend com models |
| RNF-07 | `taxes` JSON extensível (Reforma) sem reescrever AR |
| RNF-08 | Tenants com NFE_ENABLED=false: zero side-effect |

---

## 11. Critérios de aceite do MVP domínio (DoD)

1. G-NFE-SPIKE: evidência comunicação homolog **SEFAZ-SP**.  
2. G-EMIT-NFE: create→emit→`authorized` + XML + DANFE + snapshot imutável em **SP**.  
3. Cancel simples + DANFE cancelada.  
4. NumberSeries: sem colisão em teste de concorrência.  
5. Validate SN + CST 00; rejected com cStat.  
6. EX-PRE-01/03/04, EX-NET-01, EX-FIS-01, EX-PDF-01, EX-SEC-01 cobertos.  
7. G-IMPACT-OK: smoke NFS-e.  
8. Feature flag off por default em prod.  
9. OpenAPI v1 mínimo das rotas §8.  
10. `pytest` verde na entrega.

**Fora DoD MVP:** 10 UFs todas (é G-MULTI-10), ST, CCe, inutilização UI, NFC-e, estoque, contingência full.

---

## 12. Ondas / ordem de fábrica domínio

| Onda | Entrega | Gate |
|------|---------|------|
| U0 | ADR + este LLR + OpenAPI draft; pivot **SP** travado; lista 10 UFs opcional até U4 | — |
| U1 | Products + Customer nfe fields + config + flag | — |
| U2 | Draft/Invoice/Number/Snapshot/Tax min FSM | — |
| U3 | SEFAZ **SP** + sign + artifacts + cancel | G-SPIKE, G-EMIT-NFE |
| U4 | Endpoints 10 UF + QA matrix | G-MULTI-10 |
| U5 | Interestadual depth, RTC hooks, CCe backlog | — |

Paralelo: UI v0.2 stub (G-UI-WIRE) desde U1.

---

## 13. Rastreabilidade PO / reanálise

| Tema | Onde |
|------|------|
| Emissor EXEQ SEFAZ | D-01, RF-43 |
| B2B 55 / sem estoque | D-13 context, NfeProduct, RF (no stock) |
| SN + Normal | RF-22..24 |
| 10 UFs | D-12, U4; **pivot SP** libera U3 sem lista completa |
| Mesmo CNPJ/cert NFS-e | D-05, D-05a, RF-01/01a/01b, RF-42 |
| UF pivot SP | D-12; checklist §1; G-EMIT-NFE = SP |
| Greenfield / sem multa retroativa atual | D-03, RF-34; estudo impacto §0 |
| Não regredir NFS-e | D-04, RF-NFSE-*, EX-NFSE-01 |
| Snapshot dia-1 | RF-30..33 |
| Numeração | D-06, §4.4 |
| UI `allowed_actions` | FSM-04, API §8 |

---

## 14. Histórico

| Versão | Data | Nota |
|--------|------|------|
| 0.1.0 | 2026-08-05 | LLR domínio greenfield inicial; alinhado ADR-NFE-001, reanálise 1.0, UI 0.2 |
| 0.1.1 | 2026-08-05 | **UF pivot = SP** (decisão PO); checklist U0 atualizado |
| 0.1.2 | 2026-08-05 | **CNPJ + DigitalCertificate = reuso path NFS-e** (PO); RF-01a/01b |
| 0.1.3 | 2026-08-05 | **GO PO início de código** (stub first; lab 37229907000137) |
