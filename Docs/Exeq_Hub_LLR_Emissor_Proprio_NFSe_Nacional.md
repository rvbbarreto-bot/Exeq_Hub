# EXEQ Hub — LLR: Emissor Próprio NFS-e Nacional (SEFIN/ADN) + DANFSe

| Campo | Valor |
|-------|--------|
| Tipo | **Requisitos de baixo nível (LLR)** — sem implementação neste documento |
| Status | **Rascunho para fábrica v0.3** (P&O + revisão sênior + ADR-NFSE-001 + NT 008 PDF oficial) |
| Público | Engenharia, Tech Lead, QA |
| Escopo MVP | Ambiente **Nacional** apenas; EXEQ como emissor; **gera DANFSe** |
| Não escopo MVP | Municipal legado, N vendors comerciais, substituição/contencioso/manifestação |
| Código Focus | **Manter** — não deletar; não é caminho crítico de go-live |
| Corte API DANFSe gov | **2026-08-03** (NT 008/2026 **v1.02**) — trilha PDF em **paralelo** ao spike |
| ADR | `Docs/ADR_NFSE_001_Emissor_Proprio_Nacional.md` |

---

## 0. Decisões de produto travadas

| ID | Decisão | Valor |
|----|---------|--------|
| D-01 | Destino estratégico | Emissor **próprio EXEQ** |
| D-02 | Focus em operação | **Não** — Focus **não** é cutover; código **permanece** no repo |
| D-03 | Escopo fiscal MVP | **Só Ambiente Nacional** (SEFIN/ADN) |
| D-04 | DANFSe (PDF) | **EXEQ gera** no padrão NT 008/2026; **não** depender da API gov após **03/08/2026** |
| D-05 | XML | EXEQ envia DPS; SEFIN/ADN autoriza (resposta tipicamente **síncrona**); EXEQ **persiste** XML |
| D-06 | Vendors comerciais (Spedy etc.) | Fora do caminho crítico do MVP emissor próprio |
| D-07 | Reuso | Reaproveitar `issuance` FSM, TaxEngine, certificados, `NfArtifact`, porta `NfseProvider` |
| D-08 | Certificado para emissão automatizada | **Somente A1** (PKCS#12) com uso adequado a mTLS/cliente; **A3 fora do MVP** (hardware/token incompatível com SaaS multi-tenant automatizado) |
| D-09 | Trade-off emissor próprio | EXEQ assume: ciclo de vida do cert por tenant, NTs contínuas, XMLDSig, XSD, DANFSe, instabilidade de rede gov — em troca de independência do agregador |
| D-10 | Gates de release | **G-PDF** (gerador NT 008) ≠ **G-EMIT** (1ª autorização homolog); ver ADR-NFSE-001 §5 |
| D-11 | Poll esgotado | Após teto de tentativas → `failed` + alerta ops (não `polling` infinito) |

---

## 1. Pacote de estudo — documentação oficial (ADN / SEFIN / DANFSe)

O time deve ler **nesta ordem** antes de spike/fábrica. Links oficiais (Portal NFS-e):

### 1.1 Portal e notícias normativas

| # | Documento / página | Uso |
|---|-------------------|-----|
| S-01 | [Documentação técnica atual](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/documentacao-atual) | Índice mestre (manuais, XSD, anexos) |
| S-02 | [Notícia NT 008/2026 — regras DANFSe](https://www.gov.br/nfse/pt-br/noticias/se-cgnfs-e-publica-nota-tecnica-no-008-2026-com-regras-para-emissao-do-danfse) | Confirma: padrão nacional de geração do DANFSe pelos **sistemas emissores**; API gov de geração será **descontinuada** |
| S-03 | [NT 008/2026 **v1.02** (PDF oficial)](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/nt-008-se-cgnfse-danfse-20260714-v1-02.pdf) | Layout DANFSe linha a linha; suspensão API gov **03/08/2026**; URL legado API: `https://adn.nfse.gov.br/danfse/docs/index.html` |
| S-03b | [Notícia oficial prorrogação v1.02](https://www.gov.br/nfse/pt-br/noticias/danfse-novos-ajustes-de-leiaute-e-prorrogacao-do-prazo-para-adequacao) | Confirma data 3 de agosto de 2026 |
| S-04 | Seção [RTC](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc) + NTs IBS/CBS (ex. 009) | Grupos na DPS; alinhado ADR-RTC-001 |

### 1.2 Manuais de integração (contribuintes / ADN / emissor)

Baixar da pasta “Documentação atual” (S-01):

| # | Manual (nome no portal) | Uso no Hub |
|---|-------------------------|------------|
| S-10 | API — Manual de Contribuintes — Emissor Público | Fluxo emissão nacional |
| S-11 | API — Manual de Contribuintes — Guia APIs do ADN | Consulta/compartilhamento ADN |
| S-12 | API — Manual Municípios — ADN | Contexto (não é MVP municipal, mas explica ADN) |
| S-13 | Esquemas XSD NFS-e (zip atual) | Validar XML DPS/NFS-e antes do POST |
| S-14 | ANEXO I — SEFIN/ADN DPS/NFS-e | Campos oficiais |
| S-15 | ANEXO II — Pedidos/eventos | Cancelamento / eventos |
| S-16 | ANEXO B — Lista Serviço Nacional | `codigo_tributacao_nacional_iss` / NBS |
| S-17 | ANEXO C / IndOp IBS-CBS | RTC |

### 1.3 Hosts (referência interna Hub + validar nos manuais)

| Ambiente | SEFIN | ADN |
|----------|-------|-----|
| Homologação (produção restrita) | `sefin.producaorestrita.nfse.gov.br` | `adn.producaorestrita.nfse.gov.br` |
| Produção | `sefin.nfse.gov.br` | `adn.nfse.gov.br` |

Operações típicas (confirmar path/versão no manual vigente):

| Op | Método | Path (referência Hub) |
|----|--------|------------------------|
| Emitir | POST | `/SefinNacional/nfse` body com DPS (ex.: XML gzip+base64) |
| Consultar NF | GET | `/SefinNacional/nfse/{chaveAcesso}` |
| Consultar DPS | GET | `/SefinNacional/dps/{idDps}` |
| Eventos | POST/GET | `/SefinNacional/nfse/{chaveAcesso}/eventos` |

**Auth:** **somente mTLS** com certificado **ICP-Brasil** do contribuinte/prestador (A1 no MVP — D-08). **Não há** OAuth, API key ou usuário/senha na via API direta SEFIN/ADN.

### 1.4 Docs internos EXEQ (contexto, não substituem gov.br)

| Doc | Papel |
|-----|--------|
| `Docs/ADR_NFSE_001_Emissor_Proprio_Nacional.md` | **Decisão** emissor próprio / gates / trade-off |
| `Docs/Exeq_Hub_NFSe_Emission_Architecture_Reference.md` | Porta/hosts; addendum 1.1.0 aponta este LLR |
| `Docs/ADR_RTC_001_Priorizacao_Pilares.md` | IBS/CBS / versões normativas (mapper DPS) |
| `Docs/Exeq_Hub_Spedy_NFSe_Integration_Study.md` | Estudo vendor — **fora do caminho crítico** MVP próprio |
| Código Focus (`integrations/nfse/focus.py`, mappers, webhook) | **Preservar**; referência de FSM/artefatos |

### 1.5 Checklist de estudo do spike (obrigatório)

- [ ] Abrir S-01 e baixar XSD + ANEXO I/II + manuais contribuinte  
- [ ] Ler NT 008 **v1.02** linha a linha (layout DANFSe + data **03/08/2026**)  
- [ ] Confirmar hosts/paths e se POST emissão devolve NFS-e **já autorizada** na mesma resposta  
- [ ] Listar códigos de rejeição relevantes (amostra)  
- [ ] Mapear rota oficial de parametrização/convênio por município (fonte RF-01)  
- [ ] Registrar se homologação ainda devolve PDF via API (atalho só até 03/08; **proibido** como desenho final)

---

## 2. Atores e sistemas

| Ator | Responsabilidade |
|------|------------------|
| **EXEQ Hub** | Monta DPS, **XMLDSig**, mTLS (cert **A1**), envia SEFIN, reconcilia se preciso, gera DANFSe, persiste XML/PDF, FSM `NfIssue` |
| **SEFIN Nacional** | Recebe DPS, processa autorização/rejeição |
| **ADN** | Repositório/consulta nacional da NFS-e / eventos |
| **Prestador (tenant)** | CNPJ, regime, IM se exigido, certificado válido |
| **Operador / Admin QA** | Dispara emissão, consulta status, download artefatos |
| **Focus (código legado)** | Sem papel no go-live MVP; permanece no monólito |

---

## 3. Requisitos funcionais de baixo nível

### 3.1 Provisionamento e pré-condições

| ID | Requisito | Prioridade |
|----|-----------|------------|
| RF-01 | Sistema só permite emitir via emissor próprio se município IBGE estiver **aderente ao Ambiente Nacional**. Fonte de verdade: **API oficial de parametrização/convênio** (ex. rota `.../parametrizacao/{codMun}/convenio` — path exato no manual vigente); Hub mantém **cache** com refresh periódico, não lista estática como única fonte. Sem adesão → erro de negócio, sem HTTP SEFIN. | Must |
| RF-02 | Certificado digital **A1** (D-08) do prestador **ativo**, dentro da validade, apto a mTLS/cliente. Alertar expiração antes do vencimento (ops/tenant). A3 fora do MVP. | Must |
| RF-03 | Emissão exige: Provider, Customer, Service com `codigo_tributacao_nacional_iss` válido (catálogo nacional quando publicado), FiscalProfile/regra resolvida, `competence_date`, `amount_cents` > 0. | Must |
| RF-04 | TaxEngine resolve ISS (+ RTC conforme `RTC_NFSEN_MODE`) e grava snapshot **antes** do POST SEFIN. | Must |
| RF-05 | `idempotency_key` do Hub permanece única por tenant; correlacionar com `id` da DPS/`NfIssue.id` no transporte. | Must |

### 3.2 Montagem e envio da DPS

| ID | Requisito | Prioridade |
|----|-----------|------------|
| RF-10 | Mapper `to_sefin_dps` (nome sugerido) gera XML conforme XSD vigente a partir de `NfIssue` + snapshot — **sem** montar XML na View. | Must |
| RF-11 | Validação XSD/schema local **antes** do POST; falha → `rejected` ou `failed` com motivo, **sem** chamada HTTP. | Must |
| RF-12 | Adapter `SefinNfseProvider` (ou equivalente) implementa porta `NfseProvider`: `emitir`, `consultar`, `cancelar`. | Must |
| RF-13 | Transporte: mTLS; JSON nas rotas conforme manual; documento fiscal em **XML assinado (XMLDSig)** + GZip+Base64 no envelope de emissão. | Must |
| RF-13a | **Assinatura XMLDSig da DPS** segue regras oficiais de canonicalização, ordem de elementos e encoding; suite de testes com fixtures que falham se a assinatura for inválida. Nota técnica interna de implementação obrigatória no spike. | Must |
| RF-14 | Após resposta de autorização (caminho feliz síncrono) ou reconciliação, gravar referência externa (`provider_ref` / `focus_ref` reutilizado com semântica genérica **ou** ADR de rename) + raw. | Must |
| RF-15 | FSM: após envio, `submitting`. **Caminho feliz:** se o `POST /SefinNacional/nfse` retornar NFS-e **já autorizada** na mesma resposta → transicionar direto para `authorized` (sem janela de poll). Estado `polling` = **recuperação** (timeout, 5xx, resposta incompleta, queda do worker) — ver RF-20. | Must |

### 3.3 Consulta / sincronização

| ID | Requisito | Prioridade |
|----|-----------|------------|
| RF-20 | Estado `polling` **não** é o caminho feliz padrão. Usar worker/consulta com backoff **somente** para reconciliação após falha de transporte ou resposta ambígua (EX-NET-*, EX-FIS-03, EX-POL-*). Não inserir delay artificial antes de consumir resposta síncrona do POST. | Must |
| RF-21 | Status autoridade → Hub: autorizado → `authorized`; rejeitado → `rejected` (+ código/mensagem); erros de infra → retry ou `failed` conforme política. | Must |
| RF-22 | Idempotência de transição: mesmo evento de autorização não duplica outbox/artefatos. | Must |

### 3.4 Cancelamento (MVP)

| ID | Requisito | Prioridade |
|----|-----------|------------|
| RF-30 | Cancelamento simples apenas se `authorized`; justificativa com regras de tamanho alinhadas ao Hub/manual. | Must |
| RF-31 | Envia evento de cancelamento via API de eventos; em sucesso → `cancelled`. | Must |
| RF-32 | Após cancelamento autorizado, **regenerar DANFSe** com indicação visual de cancelada (marca d’água / layout NT 008). | Must |
| RF-33 | Substituição, análise fiscal contenciosa, manifestações → **fora do MVP** (backlog). | Won’t (MVP) |

### 3.5 Artefatos — XML e DANFSe (PDF)

| ID | Requisito | Prioridade |
|----|-----------|------------|
| RF-40 | Após `authorized`, persistir **XML** autorizado em `NfArtifact` + `StoredFile` (kind XML). | Must |
| RF-41 | **Gerar** DANFSe no Hub conforme **NT 008/2026 v1.02** (modelo “DANFSe v2.0” / Anexo I). Trilha **paralela** ao spike de emissão. | Must |
| RF-41a | Condições de formulário (NT 008 §2.2): retrato; tamanho **mínimo A4**; **uma única página**; papel com contraste adequado ao QR (exceto papel jornal). | Must |
| RF-41b | Campos do PDF **somente** a partir das TAGs do XML da NFS-e — não inventar informação fora do XML. | Must |
| RF-41c | Cabeçalho com logomarca oficial NFS-e, texto “DANFSe v2.0”, município emitente, ambiente; **QR Code** (mín. 1,52×1,52 cm) + texto de autenticidade conforme NT. | Must |
| RF-41d | Totais aproximados de tributos obrigatórios quando a NT exigir no leiaute. | Must |
| RF-42 | **Não** depender da API `adn.nfse.gov.br/danfse` após **03/08/2026**. Até lá, uso só como atalho lab opcional. | Must |
| RF-43 | Cancelamento: marca d’água diagonal **“CANCELADA”** (Arial ≥ 50 pt, cinza K35) — NT 008 §2.5.1. | Must |
| RF-44 | Geração idempotente por `(nf_issue, kind, versão_layout)`; falha de PDF **não** desfaz autorização — EX-PDF-*. | Must |
| RF-45 | Admin/API permitem download de XML e PDF. | Must |
| RF-46 | Marca d’água **“SUBSTITUÍDA”** (NT §2.5.2) só quando feature substituição existir. | Won’t (MVP) |
| RF-47 | Versionar template DANFSe (`danfse_layout_version`, ex. `nt008-v1.02`) nos metadados do artefato / settings. | Must |

### 3.6 Preservação Focus

| ID | Requisito | Prioridade |
|----|-----------|------------|
| RF-50 | Não remover `FocusNfseProvider`, mappers Focus, webhook Focus, testes Focus nesta entrega. | Must |
| RF-51 | Router escolhe `sefin`/`exeq_nacional` para o caminho MVP; Focus só se override explícito de lab. | Must |

### 3.7 Observabilidade e auditoria

| ID | Requisito | Prioridade |
|----|-----------|------------|
| RF-60 | Registrar em evento/`focus_status_raw` (ou equivalente): request id, HTTP status, código rejeição, tempos. | Must |
| RF-61 | Não logar certificado/senha em texto claro. | Must |
| RF-62 | Dono de NT nomeado + revisão periódica (quinzenal sugerida) das publicações do Portal. | Must (processo) |

---

## 4. Fluxos principais (felizes)

### 4.1 Emissão autorizada + artefatos

```text
[Operador] cria NfIssue (idempotency_key)
    → TaxEngine.resolve + snapshot (+ RTC shadow/emit)
    → RF-01..03 gate município(cache)/cert A1/catálogo
    → monta DPS (RF-10) + valida XSD (RF-11) + XMLDSig (RF-13a)
    → mTLS POST SEFIN (RF-12/13)
    → [feliz] resposta síncrona com NFS-e autorizada
         → FSM authorized (sem poll ativo)
    → [recuperação] timeout/5xx/incompleto → polling + GET até terminal
    → persiste XML (RF-40)
    → gera DANFSe PDF NT 008 (RF-41)  // trilha paralela de código
    → outbox nf_issue.authorized (se já existir padrão)
```

### 4.2 Cancelamento simples + PDF cancelada

```text
[Operador] cancela nota authorized + justificativa
    → POST/GET eventos cancelamento
    → FSM cancelled
    → regenera PDF com marca d’água cancelada (RF-32/43)
    → XML de evento/cancelamento armazenado se manual exigir
```

### 4.3 Rejeição fiscal pela autoridade

```text
POST ou consulta retorna rejeição com código/mensagem
    → FSM rejected
    → sem PDF de autorização
    → operador corrige dados e nova emissão (nova idempotency_key ou política de reprocesso já existente no Hub)
```

---

## 5. Fluxos de exceção (obrigatórios no desenho)

Cada EX-* deve ter: **detecção**, **estado Hub**, **mensagem ao usuário**, **retry?** , **teste**.

### 5.1 Pré-envio

| ID | Cenário | Comportamento esperado |
|----|---------|------------------------|
| EX-PRE-01 | Município não aderente ao Nacional | Bloqueia; erro de negócio; sem HTTP |
| EX-PRE-02 | Certificado ausente / expirado / revogado | Bloqueia; erro de negócio; alerta ops |
| EX-PRE-03 | Catálogo nacional sem código do serviço | Bloqueia ou `rejected` pré-envio; mensagem clara |
| EX-PRE-04 | TaxEngine sem regra ISS | Mesmo padrão atual (`pending_tax`/`rejected` — não prender fila) |
| EX-PRE-05 | XML inválido no XSD local | Não envia; `failed`/`rejected` com detalhe de schema |
| EX-PRE-06 | Valor abaixo do mínimo de política Hub (smoke) | Bloqueia conforme regra já existente |

### 5.2 Transporte / mTLS

| ID | Cenário | Comportamento esperado |
|----|---------|------------------------|
| EX-NET-01 | Falha handshake mTLS | `failed` ou retry limitado; não marcar `authorized` |
| EX-NET-02 | Timeout HTTP | Mantém `polling`/`queued` com retry backoff; idempotente |
| EX-NET-03 | HTTP 5xx SEFIN | Retry com limite; depois `failed` + alerta |
| EX-NET-04 | HTTP 4xx não fiscal (auth) | `failed`; não martelar retry |
| EX-NET-05 | Resposta ilegível / não-XML | `failed`; raw guardado para forense |

### 5.3 Negócio autoridade

| ID | Cenário | Comportamento esperado |
|----|---------|------------------------|
| EX-FIS-01 | Rejeição com código SEFIN/ADN | `rejected`; código+mensagem na UI/Admin |
| EX-FIS-02 | DPS duplicada / chave conflito | Não criar segunda autorização; reconciliar por consulta |
| EX-FIS-03 | Autorização chega após timeout local | Consulta posterior promove `authorized` (idempotente) |
| EX-FIS-04 | Cancelamento recusado | Mantém `authorized`; erro explícito; sem PDF cancelada |

### 5.4 Polling / concorrência

| ID | Cenário | Comportamento esperado |
|----|---------|------------------------|
| EX-POL-01 | Poll e “evento” futuro simultâneos | Uma transição vencedora; sem double outbox |
| EX-POL-02 | Poll esgota tentativas | `failed` + alerta ops (D-11 / ADR-NFSE-001) — **não** `polling` infinito |
| EX-POL-03 | Worker cai no meio do POST | Reprocesso seguro via idempotência |

### 5.5 DANFSe / XML

| ID | Cenário | Comportamento esperado |
|----|---------|------------------------|
| EX-PDF-01 | XML ok, geração PDF falha | Nota permanece `authorized`; flag/ops “PDF pendente”; retry de artefato; **não** reenviar DPS |
| EX-PDF-02 | Layout NT 008 desatualizado (nova NT) | Versionar template; bloquear go-live prod se checklist NT falhar |
| EX-PDF-03 | Cancelamento ok, regen PDF falha | Status `cancelled`; PDF antigo não deve parecer válida — ocultar ou marcar inválido até regen |
| EX-XML-01 | XML autorizado não retornado no GET | Retry consulta; sem inventar XML |
| EX-XML-02 | Timezone / formato data-hora / decimais / encoding inválidos no XML | Rejeição ou falha pré-envio (preferir validação local); fixture de regressão |

### 5.6 Segurança / multi-tenant

| ID | Cenário | Comportamento esperado |
|----|---------|------------------------|
| EX-SEC-01 | Tenant A não acessa artefato tenant B | RLS + checagens app |
| EX-SEC-02 | Certificado do prestador B usado no tenant A | Proibido; bind cert↔tenant/provider |

### 5.7 Legado Focus

| ID | Cenário | Comportamento esperado |
|----|---------|------------------------|
| EX-FOC-01 | Alguém aponta router para Focus em lab | Permitido só com flag explícita; não default MVP |
| EX-FOC-02 | Remoção acidental de código Focus em PR | Revisão bloqueia; RF-50 |

---

## 6. Requisitos não funcionais

| ID | Requisito |
|----|-----------|
| RNF-01 | Nenhum HTTP SEFIN/ADN fora de `integrations/` |
| RNF-02 | Testes unitários por regra (mapper, gates, map status, PDF stub) na mesma entrega |
| RNF-03 | Spike homologação **antes** de expandir UI |
| RNF-04 | Secrets (cert password) só via `TenantSecret` / storage seguro |
| RNF-05 | UX: request HTTP da API Hub **não** segura minutos; orquestra `queued`/`submitting` e devolve rápido. O POST SEFIN (síncrono no caminho feliz) roda no worker; UI consulta status. |
| RNF-06 | Acordo de engenharia: solução enxuta; sem Onion/CQRS; sem inventar tabela fora DER sem ADR |

---

## 7. Critérios de aceite do MVP (Definition of Done)

1. Spike homologação: 1 DPS autorizada com mTLS (prestador de teste).  
2. Fluxo Hub: create → submitting → **authorized** no caminho feliz síncrono; `polling` só em recuperação.  
3. XML + PDF NT 008 disponíveis no Admin.  
4. Cancelamento simples + PDF com indicação de cancelada.  
5. Pelo menos os EX-PRE-*, EX-NET-01/02, EX-FIS-01, EX-PDF-01 cobertos por teste ou roteiro QA.  
6. Código Focus intacto; router default = emissor próprio Nacional.  
7. ADR-NFSE-001 aprovado pelo PO (ou explicitamente “seguir com Proposto”).  
8. Gates: **G-PDF** e **G-EMIT** critérios do ADR §5 atendidos para o ambiente alvo.  
9. `pytest` verde na entrega.

**Fora do DoD MVP:** substituição, contencioso, manifestação, municipal, Spedy, NF-e produto, pacote contador em lote.

---

## 8. Ordem sugerida de trabalho (fábrica)

**Duas trilhas em paralelo** (calendário DANFSe: **03/08/2026**):

| Trilha A — Emissão SEFIN | Trilha B — DANFSe NT 008 |
|--------------------------|--------------------------|
| Estudo S-01…S-17 + checklist §1.5 | PDF oficial S-03 linha a linha (RF-41a…d, RF-43) |
| ADR-NFSE-001 (aprovação PO) | Protótipo gerador (autorizada + CANCELADA) → **G-PDF** |
| Spike mTLS + 1 POST síncrono + consulta + cancel | Checklist visual Anexo I + QR |
| Adapter + mapper DPS + XMLDSig + FSM sync-first | Integrar pós-`authorized` / pós-`cancelled` |
| Persistência XML + `polling` só recuperação | Hardening EX-PDF-* + `danfse_layout_version` |

Depois: QA exceções → **G-EMIT** → produção.

**Não** deixar gerador DANFSe como etapa serial após o adapter.

---

## 9. Rastreabilidade P&O

| Pergunta de gestão | Onde está neste LLR |
|--------------------|---------------------|
| Emissor próprio? | D-01, RF-12 |
| Manter Focus? | D-02, RF-50, EX-FOC-* |
| Só Nacional? | D-03, RF-01 |
| Quem gera PDF? | D-04, RF-41…43, EX-PDF-* |
| Data corte API gov PDF? | Cabeçalho, S-03, RF-42 → **03/08/2026** |
| Estudar ADN/SEFIN? | §1 pacote de estudo |
| Exceções? | §5 |
| Trade-off vs agregador? | D-09 (+ ADR-NFSE-001) |
| Gates G-PDF / G-EMIT? | D-10, ADR §5 |
| Poll infinito? | D-11, EX-POL-02 |

---

## 10. Histórico

| Versão | Data | Nota |
|--------|------|------|
| 0.1.0 | 2026-07-29 | LLR inicial pós decisões P&O/gestão |
| 0.2.0 | 2026-07-29 | Revisão sênior: 03/08, poll recuperação, A1, XMLDSig, PDF paralelo |
| 0.3.0 | 2026-07-29 | ADR-NFSE-001; NT 008 PDF oficial; RF-41a–d/47; gates G-PDF/G-EMIT; D-10/D-11; RNF-05 clarificado |
