# ADR-NFE-001 — Emissor próprio NF-e modelo 55 (SEFAZ) + DANFE EXEQ

| Campo | Valor |
|-------|-------|
| Status | **Aprovado pelo PO** |
| Data | 2026-08-05 |
| Aprovação PO | 2026-08-05 — ADR + fábrica U0–U3. **Início de desenvolvimento de código autorizado PO 2026-08-05** (inclui stub sem IE SEFAZ; G-EMIT real quando IE+credenciamento SP) |
| Tipo | ADR de produto + arquitetura de integração |
| Autores | Tech Lead + reanálise impacto NFS-e homologada (fábrica EXEQ Hub) |
| Decisões de produto (PO, conversa 2026-08-04/05) | B2B 55; **UF pivot SP**; até 10 UFs no multi; SN + Lucro P/Real; emissor EXEQ SEFAZ; sem estoque; **greenfield**; **mesmo CNPJ+cert A1 da NFS-e** |
| Relaciona | `Exeq_Hub_LLR_NFe_Dominio_SEFAZ_Greenfield.md` · `Exeq_Hub_LLR_NFe_UI_B2B_Sem_Estoque.md` v0.2 · `Exeq_Hub_NFe_Reanalise_Impacto_NFSe_Homologada.md` · `ADR_NFSE_001` (irmã serviço) · `ADR_RTC_001` |
| Código | **Fábrica liberada** (PO 2026-08-05): implementar conforme LLR domínio + UI; caminho crítico `NFE_HTTP_MODE=stub` até gate SEFAZ; **não** regressar NFS-e |

---

## 1. Decisão (texto para ata)

**Decidimos que o EXEQ Hub será emissor próprio de NF-e de produto (modelo 55, saída B2B) perante a SEFAZ**, com:

1. Montagem, assinatura e transmissão do XML **no Hub** (não agregador no caminho crítico).
2. Geração interna do **DANFE (PDF)** a partir do XML autorizado.
3. Reuso da **plataforma** já homologada na NFS-e (cert A1, FSM de emissão, artefatos, worker, multi-CNPJ, outbox), **sem** reutilizar motor ISS/DPS/SEFIN nem a entidade de serviço como nota de produto.
4. Domínio **greenfield** (não há NF-e de produto em base → sem migração de notas retroativas de produto).
5. **Sem controle de estoque** no MVP.
6. Escopo de regimes: **Simples Nacional e Lucro Presumido/Real** (cobertura operacional por ondas; ver LLR).
7. Meta de cobertura: **onda 1 = SP (São Paulo)**; até **10 UFs** na onda multi (lista em aberto, não bloqueia G-EMIT SP).

Com esta decisão:

| # | Efeito |
|---|--------|
| 1 | Caminho crítico de go-live NF-e **não** é Focus/PlugNotas/etc. |
| 2 | Agregador comercial só como **lab / contingência técnica** com flag explícita (não default). |
| 3 | NFC-e (65), estoque, entrada/compra e ST complexo ficam **fora do MVP**. |
| 4 | Certificado **A1** = **o mesmo** já usado na NFS-e (`DigitalCertificate` do CNPJ do prestador). |
| 5 | Valem o LLR de domínio SEFAZ greenfield e o LLR de UI v0.2 (trilhas paralelas). |
| 6 | **NFS-e em produção/homologação não é regredida** — bounded context irmão. |
| 7 | Emitente = **mesmo Provider/CNPJ** do path NFS-e no lab (sem segundo PFX). |

---

## 2. Contexto

- Plataforma de emissor próprio **NFS-e Nacional (SEFIN/ADN)** está homologada e documentada (ADR-NFSE-001, LLR 0.3): mTLS A1, XMLDSig, FSM, artefatos, multi-CNPJ.
- **SEFIN ≠ SEFAZ:** a prova de NFS-e **não** equivale a G-EMIT-NFE de produto.
- PO definiu destinatário **B2B modelo 55**, sem NFC-e, sem estoque, com SN **e** Normal, destino **emissor EXEQ SEFAZ**, **UF pivot SP**, até 10 UFs no multi.
- PO (2026-08-05): **UF pivot SP**; **reutilizar CNPJ + certificado A1 já implementados na plataforma para NFS-e** (sem segundo PFX).
- Premissa PO: **não existem NF-e de produto no banco** → risco de “multa por editar notas retroativas de produto” é **N/A hoje**; snapshot imutável **desde a 1ª autorização** continua Must de design (estudo de impacto §0).
- ADR-NFSE-001 §6 listava NF-e/NFC-e como **fora** do MVP de serviço — **esta ADR abre o produto mercadoria** sem reabrir o MVP NFS-e.

---

## 3. Trade-off consciente (D-NFE-09)

| Ganha | Assume |
|-------|--------|
| Independência de agregador / controle de latência e custo/nota | Ciclo de vida A1 + **roteamento multi-UF** + NTs de PL schema |
| Paridade estratégica com emissor NFSe EXEQ | Complexidade **ICMS/PIS/COFINS** (SN + Normal) e rejeições SEFAZ |
| PDF/DANFE sob controle EXEQ | Manutenção de layout e versionamento por NT |
| Greenfield (modelo limpo, zero migração produto) | Calendário realista > “copiar sefin em 1 sprint” |
| Reuso de plataforma certificada | Disciplina para **não** contaminar `NfIssue`/DPS/SEFIN |

Agregador comercial **não** é plano A. Lab via porta `NfeProvider` com kind `focus` (ou similar) só se RF-LAB do LLR.

---

## 4. Decisões técnicas travadas

| Tema | Decisão |
|------|---------|
| Documento | **NF-e modelo 55**, finalidade principal **1 – Normal** no MVP |
| Operação | **Saída** B2B; sem NFC-e 65 |
| Provider kind MVP | `sefaz` na porta **`NfeProvider`** (nova; **não** reutilizar `NfseProvider`) |
| Integração | Pacote **`integrations/sefaz_nfe/`** (ou nome equivalente); **proibido** HTTP SEFAZ em View/UI |
| Bounded context | Domínio NF-e em módulo **irmão** (`apps/nfe` **ou** subpacote isolado em issuance) — **tabelas próprias**; não colunas ISS+ICMS em `NfIssue` de serviço |
| Auth SEFAZ | Certificado **A1** ICP-Brasil; assinatura **XMLDSig** do XML NF-e; transporte conforme manual NFe 4.00 da UF |
| Cert | **A1 only** no MVP (A3 fora) |
| **Identidade emitente / cert (lab e prod)** | **Reutilizar o mesmo `Provider` (CNPJ) e o mesmo `DigitalCertificate` A1 já usados na emissão NFS-e** do tenant — **sem** cadastro paralelo de PFX “só para NF-e”. Resolução: cert **primary** (ou o ativo) do CNPJ do prestador, igual ao path SEFIN |
| Numeração | Hub controla **série + nNF** por `(tenant, company/CNPJ, serie, tpAmb)` com lock; política reserve/consume/void no LLR |
| Snapshot | Congelar emitente, dest, itens, tributos, versões de motor/layout/catalog no **submit**; imutável se `authorized` |
| Motor fiscal | Motor **mercadoria** separado do ISS; catálogo versionado; `taxes{}` extensível (RTC/IBS/CBS futuro) |
| Emissão / poll | Se SEFAZ devolver síncrono → `authorized` direto; caso lote/recibo → `polling` de reconciliação; teto → `failed` + alerta (espelha D-11 NFS-e) |
| DANFE | Gerado pelo Hub a partir do **XML autorizado**; falha de PDF **não** desfaz autorização |
| Feature flag | `NFE_ENABLED` (ou equivalente) default **off** até piloto |
| Focus / agregador | Código NFS-e Focus **intocado** por esta ADR; eventual Focus **NF-e produto** = lab only |
| Engine monstro | **Não** criar `apps/fiscal_engine` omni; evoluir módulos com fronteiras claras |
| DER | Amend v3.1 **antes** ou no 1º PR de models NF-e (sem inventar tabelas só no código) |
| Multi-UF | Catálogo de endpoints por UF/ambiente; **UF pivot homolog/go-lab = SP (São Paulo, IBGE 35)**; onda 2 = até 10 UFs happy path (lista PO em anexo) |

---

## 5. Gates de release

| Gate | Critério | Bloqueia |
|------|----------|----------|
| **G-NFE-SPIKE** | 1 XML assinado + comunicação homolog SEFAZ **SP** com evidência | Fábrica multi-UF prematura |
| **G-EMIT-NFE** | 1 NF-e **autorizada** via Hub (FSM + snapshot + XML + DANFE) em **SP** homolog | Go-live “emissor EXEQ NF-e” |
| **G-MULTI-10** | Happy path SN + Normal básico nas **10 UFs** acordadas (matriz QA) | Promessa comercial multi-UF |
| **G-UI-MVP** | LLR UI 0.2 DoD (pode iniciar em stub; emit real após G-EMIT-NFE) | UI produtiva completa |
| **G-IMPACT-OK** | Smoke NFS-e SEFIN sem regressão no mesmo release | Merge de código NF-e |

Regras:

- G-EMIT de **NFS-e** **não** substitui G-EMIT-NFE.
- É aceitável G-UI-WIRE/stub **antes** de G-EMIT-NFE.
- **Não** habilitar `NFE_ENABLED` em produção multi-tenant sem G-EMIT-NFE + runbook cert/série.

---

## 6. Escopo e fora de escopo

### Dentro (MVP domínio — ondas no LLR)

- Rascunho multi-item; validate; emit; authorize/reject/fail; cancel simples  
- Produto fiscal (sem estoque); destinatário com IE/endereço  
- Série/numeração; snapshot; artefatos XML + DANFE  
- SN + Normal **happy path** (sem ST como Must onda 1)  
- **SP** primeiro → expansão até 10 UFs   

- A1 multi-CNPJ (**mesmo** cert/CNPJ da NFS-e)  
- Idempotência, multi-tenant, feature flag  

### Fora (MVP)

- NFC-e, estoque/WMS, pedido de loja→nota, entrada/compra  
- ST / monofásico / combustível / exportação-importação complexa  
- CCe, inutilização de faixa (pós-MVP Should), manifesto DFe  
- Contingência SVC completa no dia 1 (roadmap pós G-EMIT 1 UF)  
- A3, agregador como default, reabrir redesign NFS-e  

---

## 7. Ordem de execução

| Onda | Conteúdo | Artefato |
|------|----------|----------|
| **U0** | ADR (esta) + LLR domínio + OpenAPI draft; **pivot SP** travado | Docs |
| **U1** | UI stub (LLR UI) + Product/Customer enrichment | FE + migrations leves |
| **U2** | Domain: series, draft/invoice, snapshot, FSM, tax min SN+CST00 | BE |
| **U3** | SEFAZ **SP** + sign + artifacts DANFE + cancel | G-SPIKE → G-EMIT-NFE |
| **U4** | Multi-UF (10) + matriz QA | G-MULTI-10 |
| **U5** | Interestadual/CFOP + RTC hooks + CCe scaffold + G-EMIT SP runbook | `Docs/Exeq_Hub_NFe_U5_Interestadual_CCe_G_EMIT.md` (G-EMIT-NFE ainda **ops**/homolog) |
| **U6** | Gate T0 + `GET/PUT /nfe/config/` + discard/clone | `Docs/Exeq_Hub_NFe_U6_Config_Gate.md` |
| **U7** | Outbox RF-70 `nfe.authorized` / `.rejected` / `.cancelled` | `Docs/Exeq_Hub_NFe_U7_Outbox.md` |
| **U8** | Filtros lista T1 + timeline `…/events` | `Docs/Exeq_Hub_NFe_U8_Lista_Timeline.md` |
| **U9** | NumberSeries concorrência (DoD #4) + checklist G-EMIT ops | `Docs/Exeq_Hub_NFe_U9_NumberSeries_G_EMIT.md` |
| **U10–U12** | OpenAPI NF-e + imutabilidade + UI stub MVP | `Docs/Exeq_Hub_NFe_U10_U12_Factory.md` |
| **U13** | EX-SEC multi-tenant + throttle `nfe_write` | `Docs/Exeq_Hub_NFe_U13_EX_SEC.md` |
| **RF-72** | Mídia WhatsApp DANFE/XML em `nfe.authorized` | `Docs/Exeq_Hub_NFe_RF72_Midia_WhatsApp.md` |
| **U14** | CCe 110110 (U5-CCE-01…04) | `Docs/Exeq_Hub_NFe_U14_CCe.md` |
| **U15** | Inutilização de faixa nNF (InutNFe) | `Docs/Exeq_Hub_NFe_U15_Inutilizacao.md` |
| **U16** | UI inutilização + RF-71 e-mail XML/DANFE | `Docs/Exeq_Hub_NFe_U16_UI_Inut_RF71_Email.md` |

UI e domínio **em paralelo** a partir de U0/U1 (impacto §7).

---

## 8. Aprovação

| Papel | Decisão | Data |
|-------|---------|------|
| Produto / PO | **Aprovado** — ADR + **início de desenvolvimento de código** (U1–U3 stub prioritário; SP pivot; mesmo CNPJ/cert NFS-e `37229907000137`) | **2026-08-05** |
| Produto / PO | UF pivot **SP**; IM lab `64021`; endereço Atibaia-SP; IE SEFAZ **não bloqueia** fábrica em stub | 2026-08-05 |
| Tech Lead | Executa LLR domínio + UI; `NFE_ENABLED` default off; G-IMPACT-OK | 2026-08-05 |
| Gestão | Ciente do trade-off D-NFE-09 | a confirmar operacionalmente |

### 8.1 GO de fábrica de software (PO)

**Autorizo, como PO, o início imediato do desenvolvimento** do emissor NF-e no EXEQ Hub, nos termos desta ADR e dos LLRs.

| Dentro do GO | Fora até nova autorização |
|--------------|---------------------------|
| Models, API, FSM, tax min, numeração, UI stub | Default produção multi-tenant com `NFE_ENABLED=on` sem G-EMIT-NFE |
| Adapter **stub** (`authorized` lab sem SEFAZ) | Prometer 10 UFs em produção sem G-MULTI-10 |
| Preparação SEFAZ-SP + assinatura com **mesmo** A1 | Agregador como caminho default |
| Spike HTTP SEFAZ quando IE+credenciamento existirem | Regredir ou desligar path NFS-e SEFIN |

**Lab emitente de referência:** CNPJ `37229907000137`, IM `64021`, UF SP (Atibaia), cert primary já da NFS-e.

**Efeito:** engenharia pode abrir PRs de domínio/`integrations/sefaz_nfe` (stub first) e UI conforme ordem U1→U2→U3.

---

## 9. Referências

- LLR domínio: `Docs/Exeq_Hub_LLR_NFe_Dominio_SEFAZ_Greenfield.md`  
- LLR UI: `Docs/Exeq_Hub_LLR_NFe_UI_B2B_Sem_Estoque.md`  
- Reanálise: `Docs/Exeq_Hub_NFe_Reanalise_Impacto_NFSe_Homologada.md`  
- Irmã NFS-e: `Docs/ADR_NFSE_001_Emissor_Proprio_Nacional.md`  
- RTC: `Docs/ADR_RTC_001_Priorizacao_Pilares.md`  
- Manual / XSD NF-e 4.00 e NTs (Portal NF-e / SEFAZ — baixar versão vigente no U0)  
