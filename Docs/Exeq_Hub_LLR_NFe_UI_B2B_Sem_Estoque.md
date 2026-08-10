# EXEQ Hub — LLR: UI NF-e B2B (modelo 55) sem controle de estoque

| Campo | Valor |
|-------|--------|
| Tipo | **Requisitos de baixo nível (LLR) de UI** — sem implementação neste documento |
| Status | **Rascunho para fábrica v0.2.0** (reanálise greenfield + reuso NFS-e homologada) |
| Público | Engenharia frontend, Tech Lead, QA, PO |
| Escopo MVP UI | NF-e **modelo 55**, **B2B**, **sem estoque**, **sem NFC-e**, **sem contas a receber do ERP** |
| Não escopo MVP UI | NFC-e/PDV, WMS/depósito, entrada/compra, ST complexa, CCe, inutilização, manifesto DFe, pedido→nota |
| Premissa de dados | **Não existem NF-e de produto no banco** → sem risco de multa por alteração retroativa de notas de produto *no estado atual* |
| Transporte fiscal (backend) | Fora do núcleo deste LLR: ADR/LLR domínio SEFAZ; UI consome API Hub; ver §0 e estudo de impacto |
| Base de reuso | Padrões UX/FSM da **NFS-e homologada** (lista, detalhe, cancel, cert, multi-CNPJ, async) — **documento e motor distintos** |
| Relaciona | `Exeq_Hub_NFe_Reanalise_Impacto_NFSe_Homologada.md` **1.0**; `ADR_NFE_001_Emissor_Proprio_SEFAZ.md`; `Exeq_Hub_LLR_NFe_Dominio_SEFAZ_Greenfield.md` **0.1**; LLR NFS-e 0.3; revisão comitê recalibrada 2026-08-05 |
| Código | **Não implementa** neste documento |

---

## 0. Premissas de reanálise (v0.2)

### 0.1 Greenfield de produto

| ID | Premissa |
|----|----------|
| P-01 | **Zero** registros de NF-e modelo 55 no Hub → sem migração de notas de produto, sem backfill, sem risco forense de “nota antiga de produto alterada” |
| P-02 | A partir da **primeira** autorização NF-e (lab ou prod), regras de imutabilidade e snapshot **passam a valer** (preparadas no design; custo baixo em greenfield) |
| P-03 | **NFS-e de serviço** pode ter dados vivos — desenvolvimento NF-e **não** pode regredir SEFIN/FSM/artefatos de serviço |

### 0.2 O que a NFS-e homologada entrega à UI

A UI NF-e deve **espelhar padrões já validados**, não reinventar:

| Padrão NFS-e | Aplicação na UI NF-e |
|--------------|----------------------|
| Emissão assíncrona (API rápida + status) | D-UI-11: transmitir → processando → poll |
| Gate cert A1 / multi-CNPJ | T0 + seletor emitente |
| Lista + detalhe + download artefato | T1 + T3 |
| Cancel com justificativa | T7 |
| Ambiente homolog/prod visível | Faixa em T1–T3; confirmação prod T6 |
| PDF falha ≠ desfaz autorização | EX-UI-08 |
| Separação domínio serviço | D-UI-08: telas e rotas **distintas** de NFS-e |

### 0.3 O que a NFS-e **não** entrega (não esperar “copiar tela ISS”)

- Form monoline de serviço → aqui: **itens multi-linha**, NCM, CFOP, CST/CSOSN, tPag  
- Catálogo serviço → **produtos fiscais** (T4)  
- ISS / munícipio nacional serviço → **UF emitente + ICMS**  
- DANFSe → **DANFE** (mesmo botão “PDF”, layout backend diferente)

### 0.4 Dependências de domínio (não bloqueiam protótipo stub)

| Dependência | Gate | UI stub | UI com emit real |
|-------------|------|---------|------------------|
| OpenAPI NFe + `allowed_actions[]` | U0 | mock | Must |
| NumberSeries policy | domínio | “próximo nº” mock | Must |
| Fiscal snapshot no submit | domínio | — | Must dia-1 |
| Adapter SEFAZ / 1 UF | G-EMIT-NFE | stub | Must |
| Motor SN+Normal | domínio | totals mock | Must |

Documentos: estudo de impacto §5–7; ADR/LLR domínio (a criar) para U0.

### 0.5 Parecer v0.2

| Trilha | Status |
|--------|--------|
| Protótipo + G-UI-MVP com API **stub** | **Liberado** sob este LLR |
| Emitir SEFAZ de verdade na UI | **Ressalva**: só com domínio + contrato (estudo de impacto §7) |

---

## 1. Decisões de produto travadas (UI)

| ID | Decisão | Valor |
|----|---------|--------|
| D-UI-01 | Tipo de documento | **Somente NF-e 55** (saída B2B) |
| D-UI-02 | Estoque | **Ausente** — nenhum campo, opção ou tela de saldo/depósito/lançamento |
| D-UI-03 | Regimes visíveis | **SN e Lucro Presumido/Real** (CRT define defaults de CST/CSOSN na UI) |
| D-UI-04 | UFs | **UF pivot = SP**; UI mostra emitente com UF e ambiente; multi até 10 na onda 2 |
| D-UI-05 | Destino estratégico backend | Emissor **EXEQ SEFAZ**; adapter Focus lab/plano B — **UI não expõe vendor** |
| D-UI-06 | Numeração | Número **não editável** pelo operador; UI mostra série + **próximo estimado** (T0); nº definitivo só pós-reserva backend |
| D-UI-07 | Impostos | Hub **calcula**; UI exibe; override avançado opcional (role fiscal) |
| D-UI-08 | Separação de domínio | Telas NF-e **distintas** de NFS-e; **proibido** reutilizar form de serviço/ISS |
| D-UI-09 | Reuso UX EXEQ | Lista / detalhe / cancel / multi-CNPJ / cert / async — **padrão NFS-e** |
| D-UI-10 | Hard delete | Autorizada/cancelada **nunca** apagáveis; rascunho pode ser descartado |
| D-UI-11 | Request HTTP | UI **não** aguarda SEFAZ minutos (igual NFS-e RNF-05) |
| D-UI-12 | Greenfield | Schema/API NF-e **podem evoluir** até 1º piloto sem migração de notas produto |
| D-UI-13 | Snapshot | UI **não** recalcula nota `authorized`; total/itens vêm do recurso imutável da API |
| D-UI-14 | Contrato de ações | Botões habilitados conforme `allowed_actions[]` da API (não só `if status` no front) |
| D-UI-15 | Não regredir NFS-e | Feature flag / rotas isoladas; zero mudança obrigatória no fluxo SEFIN para “caber” NF-e |
| D-UI-16 | Cert / CNPJ | Gate e emissão usam o **mesmo** `Provider` + `DigitalCertificate` já da NFS-e; UI **não** pede segundo PFX |

---

## 2. Atores e sistemas (UI)

| Ator | Responsabilidade na UI |
|------|------------------------|
| **Operador** | Cadastra produto/cliente, monta rascunho, valida, transmite, baixa XML/DANFE, cancela |
| **Admin tenant** | Config série/ambiente, cert (reuso tela cert), libera produção, troca emitente |
| **EXEQ Hub API** | Valida, FSM, impostos, envio autoridade, artefatos, `allowed_actions` |
| **Autoridade** | SEFAZ (via backend) — UI só status/código/mensagem |
| **Destinatário** | Recebe e-mail XML/DANFE se opção marcada |

---

## 3. Telas do MVP (mapa)

| ID tela | Nome | Prioridade | Rota sugerida |
|---------|------|------------|---------------|
| **T0** | Gate / pré-condições NF-e | Must | /nfe/setup ou banner em /nfe |
| **T1** | Lista de NF-e | Must | /nfe |
| **T2** | Formulário nova/editar rascunho | Must | /nfe/new · /nfe/:id/edit |
| **T3** | Detalhe da NF-e | Must | /nfe/:id |
| **T4** | Produtos fiscais (lista + form) | Must | /cadastros/produtos |
| **T5** | Clientes / destinatários (enriquecido) | Must | /cadastros/clientes (extensão) |
| **T6** | Configurações NF-e | Must | /nfe/config |
| **T7** | Modal cancelamento | Must | overlay em T3 |
| **T8** | Modal confirmação transmitir | Must | overlay em T2/T1 |

**Won’t MVP UI:** estoque, CCe, inutilização, devolução, pedido→nota, contingência UI avançada, importador planilha.

**Nav:** item de menu **NF-e** separado de **NFS-e** (evitar confusão operacional).

---

## 4. Requisitos funcionais — campos obrigatórios por tela

Legenda: **O** = rascunho ou transmitir; **R** = só transmitir; **C** = condicional; **—** = opcional.

### 4.1 T0 — Gate

Checklist (✓/✗). **Nova NF-e** desabilitada se Must falhar.

| ID | Item | Obrig. | Critério visual |
|----|------|--------|-----------------|
| RF-U-T0-01 | Emitente ativo no contexto | O | Razão + CNPJ |
| RF-U-T0-02 | IE emitente ou isento válido | O | IE / “ISENTO” |
| RF-U-T0-03 | Endereço emitente UF + mun + CEP + IBGE | O | Resumo |
| RF-U-T0-04 | CRT / regime | O | Chip |
| RF-U-T0-05 | Cert A1 válido, CNPJ alinhado — **mesmo** certificado primary da NFS-e | O | Validade OK/expirado; sem “upload NF-e” |
| RF-U-T0-06 | Série configurada | O | Nº série |
| RF-U-T0-07 | Ambiente homolog/prod | O | Faixa cor |
| RF-U-T0-08 | Próximo número **estimado** | O | Label “próximo estimado” (não promessa) |
| RF-U-T0-09 | UF do emitente exibida | O | Chip UF |
| RF-U-T0-10 | Sem UI de estoque | Must | — |
| RF-U-T0-11 | Multi-CNPJ seletor; draft dirty avisa troca | Must | — |
| RF-U-T0-12 | Feature NF-e habilitada no tenant | O | se flag off, mensagem clara |

### 4.2 T1 — Lista

**Colunas Must:** série/número · data · destinatário (doc mascarado) · valor · status · chave parcial se authorized · ambiente.

**Filtros Must:** período (default 30d) · status · busca (número, nome, doc, chave).  
**Paginação Should:** cursor/limit na API; UI “carregar mais” ou páginas.

**Status (exibição):**  
`draft` · `processando` (queued|submitting|polling|cancel_requested) · `authorized` · `rejected` · `cancelled` · `failed`  
Fonte da verdade: API; agrupamento “processando” OK se `raw_status` reservado no detalhe.

### 4.3 T2 — Formulário rascunho

#### Bloco A — Operação

| Campo | ID | Rascunho | Transmitir |
|-------|-----|----------|------------|
| Natureza da operação | RF-U-T2-A01 | O | O |
| Finalidade | RF-U-T2-A02 | O | O |
| Data emissão/saída | RF-U-T2-A03 | O | O |
| Consumidor final | RF-U-T2-A04 | O | O |
| Presença comprador | RF-U-T2-A05 | O | O |
| indIEDest | RF-U-T2-A06 | O | O |
| Série | RF-U-T2-A07 | O | O |
| Número | RF-U-T2-A08 | — | — (read-only; vazio até reserva) |
| Emitente contexto | RF-U-T2-A09 | O | O |
| `version` (concorrência) | RF-U-T2-A10 | O | O (hidden; If-Match) |

#### Bloco B — Destinatário

| Campo | ID | Rascunho | Transmitir |
|-------|-----|----------|------------|
| Cliente id ou inline | RF-U-T2-B01 | O | O |
| Doc CPF/CNPJ | RF-U-T2-B02 | O | O |
| Nome | RF-U-T2-B03 | O | O |
| IE | RF-U-T2-B04 | C | C se indIEDest=1 |
| E-mail | RF-U-T2-B05 | — | R se e-mail no envio |
| Logradouro…cMun IBGE | RF-U-T2-B06…B11 | R | R |

#### Bloco C — Itens

| Campo | ID | Transmitir |
|-------|-----|------------|
| ≥1 item | RF-U-T2-C01 | O |
| Código, descrição, NCM, CFOP, un, qtd>0, vUn | RF-U-T2-C02…08 | R |
| Origem + CSOSN ou CST | RF-U-T2-C10…11 | R |
| ICMS condicional | RF-U-T2-C12 | C |
| PIS / COFINS | RF-U-T2-C13…14 | R |

| ID | Requisito |
|----|-----------|
| RF-U-T2-C20 | **Proibido** estoque/depósito |
| RF-U-T2-C21 | Produto preenche fiscal; CFOP editável na nota |
| RF-U-T2-C22 | Impostos avançados colapsados se motor OK |
| RF-U-T2-C23 | Erro por linha destacado |
| RF-U-T2-C24 | Totais/impostos da tela draft vêm do **último validate** da API, não de fórmula só-front |

#### Blocos D–G

| Bloco | Campos | Transmitir |
|-------|--------|------------|
| D Transporte | mod frete (R), frete C, transportadora — | |
| E Pagamento | tPag, valor ≈ total, ind. pag | R |
| F Totais | read-only sticky | |
| G Observações | infCpl — | |

**Sem** “lançar estoque/contas”.

### 4.4 T3 — Detalhe

Status · série/nº · dest · valor · chave+copiar · protocolo · rejeição · timeline · XML · DANFE · ambiente · **`allowed_actions` refletidas em botões**.

Campos de auditoria leve (Should): correlation_id visível em menu “detalhes técnicos”.

### 4.5 T4 — Produto fiscal (sem estoque)

**Geral O:** código, descrição, un, vUn, ativo.  
**Fiscal O:** NCM, origem, CFOP interno; CSOSN **ou** CST; PIS/COFINS.  
**Proibido:** estoque, depósito, composição, foto loja.  
**Badge** “Fiscal incompleto” se faltar O.

### 4.6 T5 — Cliente

Extensão: IE, indIEDest default, endereço+IBGE, e-mail; badge “incompleto para NF-e”.

### 4.7 T6 — Config

Ambiente · série · próximo nº admin · e-mail auto · CRT se aplicável · confirmação **PRODUCAO** · sem expor vendor/URL SEFAZ.

### 4.8 T7 / T8

- T7: justificativa 15–255 + resumo nota.  
- T8: confirmar ambiente + e-mail opcional; **sem** estoque/contas.

---

## 5. Critérios de aceite por botão

*(Preservados de v0.1; alterações v0.2 marcadas)*

### 5.1 Global / T0

| Botão | CA |
|-------|-----|
| **Nova NF-e** | CA-BTN-001: disabled se gate falho; tooltip com itens; exige feature flag on |
| **Ir para config** | CA-BTN-002: deep-link item vermelho |

### 5.2 T1

| Ação | CA |
|------|-----|
| Filtrar | CA-BTN-012: AND; default 30d |
| Abrir | CA-BTN-011: draft→T2; terminal→T3 |
| Transmitir (opc.) | CA-BTN-013: só se `emit` ∈ allowed_actions |
| Clonar P1 | CA-BTN-014: novo id; **sem** nº |

### 5.3 T2

| Botão | CA |
|-------|-----|
| Salvar rascunho | CA-BTN-020: sem autoridade; persiste; envia `version`; **409** se conflito → UI recarrega |
| Validar | CA-BTN-021: erros por campo/item; totais API; não autoriza |
| Transmitir | CA-BTN-022: T8; exige save; processando; **Idempotency-Key** |
| Descartar | CA-BTN-023: confirm se dirty |
| +Produto / −item / cliente | CA-BTN-024…027: como v0.1 |

Edição desabilitada se status ∉ editáveis **ou** se `edit` ∉ `allowed_actions`.

### 5.4 T8

| Botão | CA |
|-------|-----|
| Confirmar | CA-BTN-030: idempotency; 202 processando; não duplicar |
| Voltar | CA-BTN-031: permanece draft |

### 5.5 T3

| Botão | CA |
|-------|-----|
| XML / DANFE | CA-BTN-040/041: só se artefato ready; PDF pendente explícito |
| E-mail | CA-BTN-042: outbox; sem re-SEFAZ |
| Cancelar | CA-BTN-043: T7 se `cancel` ∈ actions |
| Corrigir | CA-BTN-044: **política reprocesso v0.2 (§6)** |
| Refresh | CA-BTN-045: poll auto + manual |

### 5.6 T7 / T4 / T5 / T6

Mantém CA-BTN-050…081 de v0.1; T4 CA-BTN-063: após transmit, itens da nota **não** re-lêem Product (snapshot) — só rascunhos abertos.

---

## 6. FSM visível + matriz ações + reprocesso (v0.2)

### 6.1 Estados que a UI deve tratar

| Estado API | UX label | Edit form | Transmit | Artifacts | Cancel |
|------------|----------|-----------|----------|-----------|--------|
| draft | Rascunho | sim* | se actions | não | n/a (descartar) |
| queued / submitting / polling / cancel_requested | Processando | não | não | não | não |
| authorized | Autorizada | não | não | sim | se janela |
| rejected | Rejeitada | ver §6.2 | ver §6.2 | não | não |
| failed | Falhou | ver §6.2 | ver §6.2 | não | não |
| cancelled | Cancelada | não | não | sim | não |

\* e `version` / allowed_actions

**UI não inventa transição** — só chama API e re-renderiza `status` + `allowed_actions`.

### 6.2 Política de reprocesso (fechada no v0.2)

| Situação | Comportamento UI |
|----------|------------------|
| `rejected` / `failed` **sem** número consumido | **Corrigir** reabre **mesmo** draft/id (edit) |
| Número já reservado/consumido / backend manda `clone_required` | **Corrigir** cria fluxo “nova nota (clonar dados)” — nº novo; não edita autorizável quebrado |
| `authorized` | Nunca edita in-place |

Backend decide `number_consumed` / `allowed_actions`; front **não** chuta.

---

## 7. Fluxos felizes (UI)

### 7.1 Emitir (alinhado ao pipeline NFS-e)

```text
T0 gates OK → (T4/T5 se preciso) → T2
  → Salvar draft (CA-020)
  → Validar (CA-021)           // TaxEngine analog NFS-e resolve
  → Transmitir + T8 (CA-030)   // enfileira worker (padrão process_nf_issue)
  → T3 Processando → authorized
  → XML + DANFE                 // ensure_*_artifacts pattern
  → [opcional] e-mail / outbox
```

### 7.2 Rejeição / Cancel — iguais a v0.1 com política §6.2

---

## 8. EX-UI-* (exceções)

| ID | Cenário | UI |
|----|---------|-----|
| EX-UI-01 | Cert expirado | gate; CTA cert |
| EX-UI-02 | Item sem NCM no validate | highlight linha |
| EX-UI-03 | indIEDest=1 sem IE | bloqueio transmit |
| EX-UI-04 | Pagamento ≠ total | bloqueio bloco E |
| EX-UI-05 | CFOP × UF | warn/block via API |
| EX-UI-06 | Duplo transmit | debounce + idempotency |
| EX-UI-07 | Timeout autoridade | processando/failed; **nunca** authorized falso |
| EX-UI-08 | PDF pendente | authorized; PDF “pendente” (padrão EX-PDF NFS-e) |
| EX-UI-09 | Cross-tenant | 403/404 |
| EX-UI-10 | Troca emitente dirty | confirm |
| EX-UI-11 | Prod sem confirm T6 | impossível |
| EX-UI-12 | Edit authorized | bloqueado |
| EX-UI-13 | Justificativa < 15 | cancel disabled |
| EX-UI-14 | **409 conflict version** | toast + reload draft |
| EX-UI-15 | Feature flag off | T0/T1 bloqueados com mensagem |
| EX-UI-16 | Clone required pós-número | UI explica; não reusa nNF |

---

## 9. Requisitos não funcionais UI

| ID | Requisito |
|----|-----------|
| RNF-UI-01 | PT-BR; códigos SEFAZ monoespaçados |
| RNF-UI-02 | Faixa ambiente T1–T3 |
| RNF-UI-03 | Teclado; focus trap T7/T8 |
| RNF-UI-04 | Mobile: cards lista; itens empilhados |
| RNF-UI-05 | Sem PFX/senha no browser |
| RNF-UI-06 | Save draft <2s lab; transmit → processando <3s |
| RNF-UI-07 | Sem nomear vendor; “SEFAZ” só em rejeição |
| RNF-UI-08 | Shell EXEQ; convive com tela NFS-e |
| RNF-UI-09 | Contrato errors `{code, message, field_errors[]}` |
| RNF-UI-10 | Não persistir status authorized de mock em **produção** |

---

## 10. DoD MVP UI

1. T0 gate completo (§4.1) + feature flag.  
2. T4 produtos **sem** estoque; fiscal O.  
3. T2 draft multi-item + validate + transmit (stub **ou** real).  
4. T1/T3 lista/detalhe + downloads se artefatos.  
5. T7 cancel se actions.  
6. CA-BTN P0 + EX-UI-01,02,06,07,09,11,12,14.  
7. Nenhuma UI de estoque.  
8. **UI-DoD stub** ≠ **G-EMIT-NFE** (domínio).  
9. Nenhuma regressão comprovável no fluxo NFS-e (smoke checklist).  

**Fora DoD UI:** CCe, inutilização UI, ST, NFC-e, pedido→nota, 10 UF na UI (só exibir UF emitente).

---

## 11. Gates

| Gate | Critério |
|------|----------|
| **G-UI-WIRE** | Shell T1+T2+T4 campos O com mock |
| **G-UI-MVP** | DoD §10 com stub ou lab |
| **G-EMIT-NFE** | 1ª NF-e autorizada (LLR domínio) — **fora deste doc** |
| **G-IMPACT-OK** | Estudo impacto 1.0 lido; feature flag; sem tocar DPS/SEFIN em PR UI |

---

## 12. Ordem de fábrica UI (v0.2)

| # | Entrega | Pode stub? |
|---|---------|------------|
| 1 | T6 + T0 + seletor + flag | sim |
| 2 | T4 produtos | sim |
| 3 | T5 clientes | sim |
| 4 | T1 lista + estados | sim |
| 5 | T2 + version/409 | sim |
| 6 | T8 + transmit + poll (`allowed_actions`) | **contrato mínimo** |
| 7 | T3 downloads | sim até artifacts |
| 8 | T7 cancel | domínio |
| 9 | Hardening EX-UI + mobile | — |

Paralelo: OpenAPI + domínio (estudo impacto U0–U2).

---

## 13. Rastreabilidade

| Tema | Onde |
|------|------|
| Greenfield / sem multa retroativa produto | P-01, D-UI-12, estudo impacto §0 |
| Reuso NFS-e homologada | §0.2–0.3, D-UI-09, §7.1 |
| Não regredir NFS-e | P-03, D-UI-15, G-IMPACT-OK |
| Snapshot dia-1 | D-UI-13, CA-BTN-063 |
| Numeração estimada | D-UI-06, RF-U-T0-08 |
| Reprocesso fechado | §6.2 |
| Escopo PO B2B/sem estoque/SN+Normal/SEFAZ | D-UI-01…05 |

---

## 14. Histórico

| Versão | Data | Nota |
|--------|------|------|
| 0.1.0 | 2026-08-05 | LLR UI inicial: telas, campos, CA-BTN |
| **0.2.0** | **2026-08-05** | Reanálise: greenfield; reuso NFS-e; `allowed_actions`; version/409; número estimado; reprocesso; gates G-IMPACT; parecer UI stub liberado |
