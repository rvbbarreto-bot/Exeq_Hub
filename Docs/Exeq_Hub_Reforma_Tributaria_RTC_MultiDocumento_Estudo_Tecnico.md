# EXEQ Hub — Estudo Técnico: Reforma Tributária do Consumo, Multi-Documento Fiscal e Integração Contábil

| Campo | Valor |
|-------|-------|
| Versão | **0.1.0-draft** |
| Data | 2026-07-26 |
| Audiência | Direção, gestão de produto, engenharia sênior, jurídico/contábil parceiro |
| Status | Estudo de análise — **não é ADR aprovado**; não autoriza criação de tabelas/endpoints fora de v3.1 |
| Hierarquia docs | Contrato → v1 → v2 → v3.1 → NFS-e Ref. → **este estudo** → v4 → v5 |
| Relação com Hub atual | Escopo vigente = **NFS-e (serviço)** + cobrança + DAS. NF-e/NFC-e, locação de bens e portal contábil = **programa futuro** |

> **Aviso de honestidade técnica:** “zero gap” absoluto é **inatingível** enquanto o Fisco publicar NTs, tabelas CST/cClassTrib e atos CGIBS/RFB em ritmo contínuo (ex.: NT 2025.002 já passou por dezenas de revisões até v1.50 em 2026). O que este documento entrega é: (1) cobertura estrutural das obrigações conhecidas; (2) matriz de prioridade executável; (3) inventário de gaps do Hub vs. lei/NT; (4) processo de **governança de conformidade contínua** para que gaps residuais sejam detectados e fechados antes de produção.

---

## 1. Sumário executivo (direção)

### 1.1 O que mudou no Brasil (visão de negócio)

A Emenda Constitucional **132/2023** e a Lei Complementar **214/2025** substituem, em transição até **2033**, o modelo fragmentado (PIS, COFINS, IPI, ICMS, ISS) por um **IVA dual**:

| Novo tributo | Competência | Substitui (destino) |
|--------------|-------------|---------------------|
| **CBS** | União | PIS + COFINS (extinção operacional a partir de 2027) |
| **IBS** | Estados + Municípios + DF (Comitê Gestor) | ICMS + ISS (extinção plena em 2033) |
| **IS** (Imposto Seletivo) | União (extrafiscal) | Incide sobre bens/serviços nocivos à saúde/meio ambiente (não é IVA) |

Princípios operacionais que **quebram** ERPs e emissores desenhados no modelo antigo:

1. **Não cumulatividade ampla** (crédito financeiro).
2. **Destino** como regra de local do fato gerador (fim da guerra fiscal “clássica” de origem).
3. **Tributo “por fora”** do preço (IBS/CBS destacados; não compõem receita da mesma forma que ICMS “por dentro”).
4. **Documento fiscal como peça central da apuração** (não só obrigação acessória).
5. **Split payment** (segregação do tributo na liquidação financeira) — a nota vira input do arranjo de pagamento.
6. **Classificação tributária padronizada** por item: **CST** + **cClassTrib** (e equivalentes na NFS-e Nacional).

### 1.2 Implicação direta para o EXEQ Hub

| Capacidade desejada | Dependência Reforma | Dependência produto Hub |
|---------------------|---------------------|-------------------------|
| Continuar emitindo **NFS-e Nacional** (Atibaia / Focus `nfsen`) | **NT SE/CGNFS-e** (RTC) — grupos IBS/CBS na DPS; fórmulas BC por período | Adequar mapper Focus + TaxEngine + UI |
| Emitir **venda de produto (NF-e 55)** | **NT 2025.002-RTC** (Grupo UB, W03, CST/cClassTrib) | Novo domínio + adapter Focus NF-e |
| Emitir **NFC-e 65** (varejo) | Mesma família NT 2025.002 + CSC/ contingência | Escopo varejo explícito |
| **Locação de produtos** | Pode ser NFS-e **e/ou** NF-e (remessa/retorno) + regras IBS/CBS | Decisão fiscal contábil **antes** do código |
| Integração **escritório contábil** | XML com grupos RTC + eventos + retenção legal | Canal entrega + papel `accountant` |

**Decisão de gestão recomendada:** tratar Reforma + multi-documento + contábil como **Programa “RTC / DF-e Unificado”** (2026–2033), não como sprint da tela “Emitir NFS-e”.

### 1.3 Prioridade macro (ver matriz §10)

1. **P0 — Sobrevivência 2026:** destaque IBS/CBS na **NFS-e Nacional** (e NF-e se já houver roadmap de produto) — rejeição SEFAZ/ADN se layout inválido.
2. **P1 — 2027:** CBS plena, fim PIS/COFINS no fluxo, Simples/híbrido, início split payment.
3. **P2 — Multi-documento:** NF-e venda + artefatos + contábil XML.
4. **P3 — Locação** (natureza fechada) + NFC-e se houver caso.
5. **P4 — 2029–2033:** coexistência ICMS/ISS×IBS, partilha destino, créditos transitórios.

---

## 2. Base normativa (fonte primária e infralegal)

### 2.1 Hierarquia normativa relevante

```
CF/88 (arts. alterados pela EC 132/2023) + ADCT (arts. 124–134 tipicamente)
    │
    ├── LC 214/2025 — IBS, CBS, IS (instituição + regras gerais)
    ├── LC 227/2026 — Comitê Gestor do IBS (CG-IBS)
    ├── Atos conjuntos RFB / CGIBS (penalidades, split payment, manuais)
    ├── Resoluções CGIBS / Decretos (ex.: Dec. 12.955/2026 quando aplicável)
    │
    ├── ENCAT / Portal NF-e — NT 2025.002-RTC (NF-e / NFC-e) + schemas XSD
    ├── SE/CGNFS-e — NTs RTC NFS-e Nacional (ex.: NT 009/2026) + Anexos VI/VII
    └── Provedores (Focus NFe, etc.) — espelho dos leiautes oficiais
```

### 2.2 Fontes oficiais a versionar no cofre de conformidade do Hub

| Artefato | Onde | Uso no Hub |
|----------|------|------------|
| EC 132/2023 | Planalto | Cronograma ADCT |
| LC 214/2025 | http://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm | Fato gerador, BC, regimes, SN, split, créditos |
| LC 227/2026 | Planalto | CG-IBS |
| NT 2025.002-RTC (versão corrente, ex. **v1.50** em 03/06/2026) | Portal Nacional NF-e | Schema NF-e/NFC-e Grupo UB / W03 |
| Tabelas CST / cClassTrib / cCredPres | Portal NF-e (Diversos / Informes Técnicos) | Motor de classificação |
| NT SE/CGNFS-e **009** (04/06/2026) + Anexo VI v1.04.00 + Anexo VII IndOp | https://www.gov.br/nfse | DPS Nacional IBS/CBS |
| Manual Split Payment (Ato Conjunto RFB/CGIBS nº 2/2026) | RFB/CGIBS | Integração financeira futura |
| Doc Focus (nfse / nfsen / nfe) | doc.focusnfe.com.br | Adapter concreto |

**Processo obrigatório (anti-gap):** owner de conformidade atualiza **changelog normativo** a cada NT; engenharia não mergeia mapper fiscal sem checklist de versão de schema.

---

## 3. Modelo tributário alvo (baixo nível)

### 3.1 Substituição e coexistência

```
ANTES (até início da transição plena)
  PIS + COFINS + IPI + ICMS + ISS
       │
2026   │  + IBS teste 0,1% + CBS teste 0,9% (recolhimento dispensável se OA OK)
       │  + obrigações de destaque em DF-e
2027   │  − PIS/COFINS (em regra)
       │  + CBS referência; + IS; IPI ~0 (ressalva ZFM)
       │  + IBS ainda reduzido; split payment inicia
2029–32│  ICMS/ISS: 90%→60% da alíquota vigente; IBS sobe
2033   │  − ICMS − ISS; IBS + CBS plenos
```

Alíquotas-teste **2026** (ADCT / LC 214 — ano-teste):

| Tributo | Alíquota-teste |
|---------|----------------|
| CBS | **0,9%** |
| IBS | **0,1%** (composição estadual/municipal conforme regra do período) |
| Soma “IVA teste” | **1,0%** |

### 3.2 Fato gerador e base (conceitos LC 214)

- **Incidência ampla** sobre operações onerosas com bens e serviços (incluindo, em hipóteses legais, ativo, uso/consumo).
- **Base de cálculo** tipicamente o valor da operação, com exclusões/inclusões previstas em lei (não reutilizar fórmulas ISS “município X” sem revisão).
- **Local:** regra de **destino** (domicílio do adquirente / consumo) — impacto direto em:
  - `cMunFGIBS` (NF-e);
  - município IBGE na NFS-e;
  - partilha IBS UF × Município.
- **Não cumulatividade:** crédito na aquisição → débito na venda; documento fiscal é elo da cadeia de crédito.

### 3.3 Imposto Seletivo (IS)

- Extrafiscal; lista de bens/serviços (fumo, bebidas, veículos sob critérios, mineração, etc. — conforme LC 214).
- **Não** confunde com IBS/CBS.
- No XML NF-e: bloco **UB01** (CSTIS, cClassTribIS, vBCIS, pIS/adRemIS, qTrib, vIS).
- Exportações e alguns setores (ex.: energia/telecom conforme vedações legais) fora do IS.

### 3.4 Regimes especiais / reduzidos (inventário para cadastro)

O motor do Hub precisará de **tabela parametrizável** (não hardcode) para:

| Família | Exemplos (LC 214) | Efeito no DF-e |
|---------|-------------------|----------------|
| Redução 60% | saúde, educação, medicamentos, alimentos (grupos) | CST/cClassTrib + pRedAliq |
| Redução 30% | profissões intelectuais regulamentadas | idem |
| Alíquota zero | cesta básica nacional | CST específico |
| Imunidade | exportações (com manutenção de créditos) | grupos condicionais |
| ZFM / ALC | arts. aplicáveis LC 214 | gALCZFMCBS / gIBSZFM |
| Monofasia | combustíveis etc. | gIBSCBSMono |
| Cashback | famílias baixa renda (art. relacionados) | campos de devolução/tributo |
| Plataformas digitais | responsabilidade arts. 22–23 LC 214 | cadastro + apuração |

---

## 4. Cronograma operacional 2026–2033 (matriz tempo × sistema)

| Quando | Marco | Impacto sistema | Severidade se falhar |
|--------|-------|-----------------|----------------------|
| Jan/2026 | Ano-teste IBS/CBS | Apuração informativa + destaque | Alta (OA) |
| Jul/2026 | Homologação NF-e com validações UB | Testes Focus/SEFAZ | Alta |
| **03/08/2026** | Produção: rejeição NF-e/NFC-e sem IBS/CBS (regime regular) | Emissão produto bloqueada | **Crítica** |
| Set/2026 | Decisão SN: IBS/CBS no DAS vs. regime híbrido (art. 41 §3º) | Flag tenant + UI | Alta |
| Jan/2027 | CBS plena; −PIS/COFINS; +IS; SN/MEI no destaque; split inicia | Motor fiscal + financeiro | **Crítica** |
| 2027–2028 | IBS reduzido + CBS plena | Coexistência de regras | Alta |
| 2029–2032 | ICMS/ISS 90%→60%; IBS referência | Dois “mundos” no mesmo XML | **Crítica** |
| 2033 | −ICMS −ISS | Remoção de ramos legado | Alta |

**Hub hoje (NFS-e):** o marco análogo de layout é o **cronograma SE/CGNFS-e** (NT 009 e anteriores) — acompanhar portal gov.br/nfse; não assumir a mesma data 03/08/2026 automaticamente para DPS Nacional sem NT de implantação publicada.

---

## 5. Documentos fiscais eletrônicos (DF-e) — detalhe de leiaute

### 5.1 NF-e (55) / NFC-e (65) — NT 2025.002-RTC

#### 5.1.1 Identificação e finalidades novas

- Município fato gerador IBS/CBS: **`cMunFGIBS`** (Grupo B).
- Finalidades adicionais de **nota de débito/crédito** (ajuste RTC): campos `tpNFDebito` / `tpNFCredito`.
- Grupo de **antecipação de pagamento** e referências cruzadas de DF-e (conforme NT).

#### 5.1.2 Por item — Grupo **UB** (`det/imposto`)

```
det/imposto
  └── UB  Informações IBS/CBS/IS
        ├── UB01  Bloco IS (quando aplicável)
        │     CSTIS, cClassTribIS, vBCIS, pIS|adRemIS, uTrib, qTrib, vIS
        └── UB12  Bloco IBSCBS
              ├── CST (3) + cClassTrib (6) + indDoacao?
              └── gIBSCBS
                    ├── vBC (base única IBS+CBS)
                    ├── gIBSUF   (alíquota UF, diferimento, redução, cashback…)
                    ├── gIBSMun (análogo município)
                    ├── vIBS
                    └── gCBS (+ gALCZFMCBS quando ZFM/ALC)
              └── subgrupos condicionais por CST/cClassTrib:
                    gTribRegular | gIBSCBSMono | gCredPresOper | gTransfCred | …
```

#### 5.1.3 Totais — Grupo **W03**

- `ISTot`, `IBSCBSTot` (aberturas UF / Mun / CBS / monofásico).
- **`vNFTot`**: total da NF **incluindo** IBS/CBS/IS (tributo por fora).
- Regra crítica de produto: **não** misturar legado `vNF` sem revisão de UX de “valor da operação” vs “total com IVA dual”.

#### 5.1.4 Classificação — CST × cClassTrib

| Código | Papel |
|--------|-------|
| **CST** (3 dígitos) | Situação tributária IBS/CBS (ex.: 000 integral, 200 reduzida, 410 imune, 510 diferimento, 620 monofásico, 800 transf. crédito…) |
| **cClassTrib** (6 dígitos) | Liga o item a dispositivo da LC 214; dirige validações e apuração assistida |

**Engine rule:** o Hub **não inventa** CST/cClassTrib; consome **tabela oficial versionada** + regras de obrigatoriedade de subgrupos (validador RTC).

Exemplos de obrigatoriedade de grupo (síntese de guias alinhados à NT):

| CST (família) | Grupo exigido (típico) |
|---------------|------------------------|
| 000, 200, 510, 515, 550 | `gIBSCBS` tributação padrão |
| 620 | `gIBSCBSMono` |
| 800 | `gTransfCred` |
| 410, 810, 830 | sem grupo de tributação padrão (conforme tabela) |

### 5.2 NFS-e Nacional (DPS) — NT SE/CGNFS-e 009/2026 e anexos

**Âmbito:** padrão nacional (ADN/SEFIN) — alinhado ao Focus layout `nfsen` do Hub.

#### 5.2.1 Anexos oficiais

| Anexo | Conteúdo |
|-------|----------|
| **Anexo VI** Leiautes RN_RTC_IBSCBS **v1.04.00** | Layout consolidado DPS/NFS-e com IBS/CBS + RN |
| **Anexo VII** IndOp_IBSCBS **v1.02.00** | Códigos `cIndOp` (indicador de operação) — art. 11 LC 214 |

#### 5.2.2 Mudanças estruturais (baixo nível)

| Tema | Detalhe técnico |
|------|-----------------|
| CNPJ alfanumérico | Tipo de campo CNPJ: **N → C** (jul/2026+) — quebra validadores só-dígito |
| Finalidade | `finNFSe`: 0 regular, 1 crédito, 2 débito |
| Ajustes | `tpNFSeDebito` / `tpNFSeCredito` + grupo **`gIBSCBSAjuste`** (`vIBS`, `vCBS`) |
| Ajuste BC | Merge `vDedRed` + `gReeRepRes` → **`vAjusteBC`** |
| Fórmulas BC IBS/CBS | Até **2026**: `vBC = vServ − descIncond − ajustes − vISSQN − vPIS − vCOFINS`; **2027–2032**: sem PIS/COFINS na fórmula (só ISSQN entre os legados citados na NT) |
| Simples | `regApIBSCBSSN`, grupo **`gTribSN`**, status “optante pendente”, regime híbrido |
| Imóveis / bens móveis | Reestruturação grupos (locação imóveis / `bensMoveis`) |
| Pagamento vinculado | Grupo **`gPgtoVinc`** (elo nota ↔ liquidação / split) |
| Consumidor final | Reinserção `indFinal` |

#### 5.2.3 Impacto no código atual do Hub (gap explícito)

Hoje o Hub:

- Resolve **ISS municipal** via TaxEngine / perfil fiscal.
- Monta emissão Focus **sem** modelo de domínio para IBS/CBS/IS na DPS.
- Catálogo de serviço nacional (Anexo B) **não** contém CST/cClassTrib/cIndOp RTC.

**Gap P0:** mapper Focus `nfsen` + snapshot fiscal + UI devem passar a carregar grupos RTC **antes** da data de rejeição ADN publicada no cronograma oficial NFS-e.

### 5.3 CT-e / MDF-e / outros

Fora do MVP recomendado. Manter na matriz como **P4/Could** salvo cliente logístico.

---

## 6. Locação de produtos — análise fiscal (sem ambiguidade de produto)

### 6.1 Hipóteses

| Hipótese | Documento típico | Tributos na transição | Observação |
|----------|------------------|----------------------|------------|
| **H1** Locação como prestação de serviço | **NFS-e** | ISS (transição) + IBS/CBS na DPS | Alinhado ao Hub atual |
| **H2** Remessa de bem para locação / retorno | **NF-e** (CFOP remessa/retorno) | ICMS (transição) + IBS/CBS Grupo UB | Exige estoque/ativo + CFOP |
| **H3** Mista | NFS-e (serviço) + NF-e (remessa) | Dois motores | Mais comum em locadoras estruturadas |

### 6.2 Decisão bloqueante (gestão)

Antes de qualquer sprint de “locação”:

1. Parecer contábil/jurídico por **NCM/atividade CNAE** do tenant.
2. Matriz operação → `{doc_type, CFOP?, cIndOp?, CST, cClassTrib}`.
3. ADR no repositório Docs.

**Risco:** implementar só NFS-e para locadora que precisa de remessa = gap fiscal e rejeição/passivo.

---

## 7. Split payment, meios de pagamento e Hub financeiro

### 7.1 Conceito

Na liquidação (Pix, débito, arranjos), o valor de IBS/CBS é **segregado** e enviado ao Fisco; o fornecedor recebe o líquido. A **NF** carrega os valores que o arranjo consulta.

### 7.2 Requisitos de sistema (baixo nível)

| Componente | Requisito |
|------------|-----------|
| Emissão | Valores IBS/CBS **exatos** e classificados (CST/cClassTrib) |
| Vínculo | Identificador de pagamento / `gPgtoVinc` / token de segregação |
| Ordem temporal | DF-e autorizado **antes** ou sincronizado com liquidação (conforme manual) |
| Billing Hub (Inter/C6) | Avaliar se o provedor participa do arranjo split; senão, documentar limitação |
| Contábil | XML + informe de segregação para conciliação |

### 7.3 Faseamento

- **2026:** foco em **destaque correto** (dispensa de recolhimento condicionada a OA).
- **2027+:** integração split = projeto próprio (não embutir no primeiro PR de layout).

---

## 8. Simples Nacional, MEI e regime híbrido

| Tema | Regra | Impacto Hub |
|------|-------|-------------|
| Destaque DF-e SN/MEI | Obrigatoriedade reforçada a partir de **jan/2027** (NF-e); NFS-e conforme NT/cronograma | Flag `tax_regime` + validações |
| Opção set/2026 | Recolher IBS/CBS no DAS **ou** “por fora” (regime regular não cumulativo) — LC 214 art. 41 §3º | Cadastro tenant + prazo UI |
| Crédito do adquirente | Art. 47 — crédito limitado se fornecedor SN sem opção “por fora” | Aviso na emissão B2B |
| Campos NFS-e | `regApIBSCBSSN`, `gTribSN` | Mapper + testes |

Tenants Hub atuais (`simples_nacional`) **não** podem ser tratados como “só ISS” a partir de 2027.

---

## 9. Integração com escritório de contabilidade

### 9.1 Necessidades do contador (requisitos)

1. **XML autorizado** completo (com grupos RTC).
2. **PDF** (DANFSe / DANFE).
3. Metadados: chave, CNPJ, período, modelo, status, eventos (cancelamento, CCe, ajuste).
4. Entrega em lote por competência.
5. Rastreio de download / e-mail.
6. Separação multi-cliente (vários tenants sob o mesmo escritório).

### 9.2 Desenho técnico recomendado (camadas)

```
Emission Store (NfIssue / futuro FiscalDocument)
        │
        ├── ArtifactService → XML + PDF (já existe parcialmente p/ NFS-e)
        │
        ├── AccountingPackageBuilder
        │     • zip por competência
        │     • manifesto JSON (chaves, hashes SHA-256)
        │
        ├── DeliveryChannel
        │     • email (SMTP)
        │     • download autenticado (portal)
        │     • webhook (escritório ERP)
        │
        └── AccessControl
              • role accountant | office_link (N:N office↔tenant)
```

### 9.3 Gaps atuais

- Sem papel contador / vínculo escritório.
- Sem pacote de competência.
- XML RTC incompleto = pacote **inútil** para apuração IBS/CBS.

**Prioridade:** P1.5 — após P0 de layout RTC na emissão.

---

## 10. Matriz de prioridade (MoSCoW × tempo × criticidade)

Legenda: **C** = crítico negócio/compliance · **A** = alto · **M** = médio · **B** = baixo

### 10.1 Programa RTC — onda 0 (agora → ago/2026)

| ID | Entrega | MoSCoW | Crit. | Dependência | Gap Hub |
|----|---------|--------|-------|-------------|---------|
| RTC-01 | Inventário normativo versionado (EC/LC/NTs) + owner | Must | C | — | Inexistente |
| RTC-02 | Modelo de dados `TaxClassification` (CST, cClassTrib, cIndOp, vigência) | Must | C | RTC-01 | Inexistente |
| RTC-03 | Adequar emissão **NFS-e Nacional** aos grupos IBS/CBS (NT 009+) via Focus | Must | C | RTC-02 | Mapper legado ISS-only |
| RTC-04 | Fórmulas BC por período (≤2026 vs 2027–2032) + testes unitários | Must | C | RTC-03 | TaxEngine ISS-only |
| RTC-05 | UI emissão: exibir/editar classificação RTC (com defaults seguros) | Must | A | RTC-03 | Select serviço sem CST |
| RTC-06 | CNPJ alfanumérico em validadores | Must | A | NT 009 | Validação só dígitos |
| RTC-07 | Homologação Focus/ADN com XML real RTC | Must | C | RTC-03 | — |
| RTC-08 | Se roadmap NF-e: Grupo UB + W03 + rejeição 03/08/2026 | Must* | C | Produto NF-e | Fora do DoD atual |

\*Obrigatório **somente** se a direção aprovar NF-e no mesmo horizonte; senão documentar **não-escopo** explícito.

### 10.2 Onda 1 (2H2026 → 2027)

| ID | Entrega | MoSCoW | Crit. |
|----|---------|--------|-------|
| RTC-10 | Decisão SN híbrido (set/2026) no cadastro tenant | Must | C |
| RTC-11 | Campos SN na DPS (`gTribSN`, `regApIBSCBSSN`) | Must | C |
| RTC-12 | Notas de ajuste crédito/débito NFS-e | Should | A |
| RTC-13 | Pacote contábil XML+PDF por competência + e-mail | Should | A |
| RTC-14 | Papel `accountant` + vínculo escritório↔tenant | Should | A |
| RTC-15 | Estudo split payment × Inter/C6 (spike) | Should | A |
| RTC-16 | Remoção/neutralização PIS/COFINS no cálculo pós-2026 | Must | C |

### 10.3 Onda 2 — Multi-documento (após ADR)

| ID | Entrega | MoSCoW | Crit. |
|----|---------|--------|-------|
| DOC-01 | ADR “FiscalDocument” (nfse\|nfe\|nfce) sem quebrar `NfIssue` | Must | C |
| DOC-02 | Catálogo produto (NCM, origem, unidade) | Must | C |
| DOC-03 | Adapter Focus NF-e + Grupo UB | Must | C |
| DOC-04 | CFOP + natureza operação + ICMS coexistência 2029–32 | Must | C |
| DOC-05 | Locação: matriz H1/H2/H3 após parecer | Must | C |
| DOC-06 | NFC-e + CSC + contingência | Could | M |
| DOC-07 | IS (Imposto Seletivo) por NCM | Should | A |
| DOC-08 | Portal contador (UI) | Could | M |
| DOC-09 | CT-e/MDF-e | Won’t (agora) | B |

### 10.4 Onda 3 — Transição 2029–2033

| ID | Entrega | MoSCoW | Crit. |
|----|---------|--------|-------|
| TRN-01 | Motor dual ICMS/ISS × IBS (frações anuais) | Must | C |
| TRN-02 | Créditos transitórios / saldos | Should | A |
| TRN-03 | Partilha destino / cMunFGIBS auditável | Must | C |
| TRN-04 | Desligar ramos ISS/ICMS em 2033 | Must | A |

### 10.5 Matriz esforço × valor (gestão)

```
        Alto valor compliance
                │
   RTC-03,04,07 •••••  DOC-03 (se NF-e)
                │
   RTC-10,11    •••    DOC-05 locação
                │
   RTC-13,14    ••     DOC-08 portal
                │
   DOC-06 NFC-e •      DOC-09 CT-e
                └──────────────────── esforço
                  baixo              alto
```

---

## 11. Arquitetura alvo no Hub (encaixe com v2 / v3.1)

### 11.1 Princípio

Não substituir TaxEngine por “cálculo Focus”. Manter:

`View → Serializer → Application Service → Domain/Tax Engine → Provider Port → Focus/ADN`

### 11.2 Novos bounded contexts (proposta de estudo — exige ADR)

| Contexto | Responsabilidade |
|----------|------------------|
| `tax_classification` | Tabelas CST/cClassTrib/cIndOp versionadas |
| `rtc_assessment` | Cálculo IBS/CBS/IS + coexistência legado |
| `fiscal_document` | Generalização emissão (ou adapters por modelo) |
| `accounting_delivery` | Pacotes e canais ao escritório |
| `split_payment` (futuro) | Integração arranjo / informe segregação |

### 11.3 Impacto DER (não implementar sem v3.x amend)

Campos/entidades **candidatos** (lista para ADR-DB):

- `TaxClassTableVersion`, `TaxClassCode` (CST, cClassTrib, vigência_inicio/fim).
- Em item de documento: `cst_ibscbs`, `c_class_trib`, `v_bc_ibscbs`, `p_ibs_uf`, `p_ibs_mun`, `p_cbs`, `v_ibs`, `v_cbs`, `cst_is`, …
- Snapshot imutável pós-autorização (igual padrão atual de emissão).
- `AccountingOffice`, `OfficeTenantLink`, `AccountingDeliveryJob`.

**Proibido:** inventar tabelas em PR sem atualizar v3.1.

### 11.4 Testes obrigatórios (política engenharia)

Toda regra RTC:

1. Teste unitário de fórmula BC por ano-calendário.
2. Fixture XML/JSON Focus golden file por NT version.
3. Matriz CST → subgrupo obrigatório.
4. Não mergear só com “parece autorizado em sandbox”.

---

## 12. Inventário de gaps (Hub atual × Reforma × multi-doc × contábil)

| # | Gap | Domínio | Severidade 2026 | Severidade 2027+ |
|---|-----|---------|-----------------|------------------|
| G01 | Sem grupos IBS/CBS na emissão NFS-e | NFS-e | Crítica (quando ADN exigir) | Crítica |
| G02 | TaxEngine só ISS/municipal | Fiscal | Alta | Crítica |
| G03 | Sem CST/cClassTrib/cIndOp | Classificação | Crítica | Crítica |
| G04 | Validação CNPJ só numérica | Cadastro | Alta (jul/2026+) | Alta |
| G05 | Sem NF-e/NFC-e | Produto | N/A se fora escopo | Crítica se venda produto |
| G06 | Sem modelo locação H1/H2/H3 | Produto | Média | Alta |
| G07 | Sem split payment | Financeiro | Baixa (2026) | Alta |
| G08 | Sem pacote/portal contábil | Contábil | Média | Alta |
| G09 | Sem governança de versão de NT | Ops | Crítica | Crítica |
| G10 | Documentação v1/v3.1 sem RTC | Docs | Alta | Alta |
| G11 | Simples sem opção híbrida | Cadastro | Alta (set/2026) | Crítica |
| G12 | Fórmulas BC sem corte 2026/2027 | Fiscal | Alta | Crítica |
| G13 | IS não modelado | Fiscal | Média (NFS-e) | Alta (NF-e bens) |
| G14 | Coexistência ICMS/ISS×IBS 2029–32 | Fiscal | Baixa hoje | Crítica depois |
| G15 | Plataformas digitais (resp. LC 214) | Compliance | Baixa | Média/Alta se marketplace |

---

## 13. Controles para “não ter gap” (governança)

### 13.1 Ritual mensal (obrigatório)

1. Diff Portal NF-e (NT 2025.002) + Portal NFS-e (NTs SE/CGNFS-e).
2. Diff tabelas CST/cClassTrib.
3. Diff release notes Focus.
4. Abrir issues `compliance/rtc-*` com severidade.
5. Atualizar este documento (changelog §15).

### 13.2 Definition of Ready (feature fiscal)

- Referência legal/NT + versão schema.
- Matriz de campos XML/JSON.
- Casos de teste (autorização + rejeição).
- Impacto Simples/regular.
- Impacto contábil (XML still valid?).

### 13.3 Definition of Done

- Testes verdes + golden file da NT.
- Feature flag por tenant/ambiente.
- Runbook de rollback (emitir modo legado **só** se legalmente permitido).

### 13.4 O que **não** garante zero gap

- Copiar layout de um único ERP concorrente.
- Confiar só em sandbox sem rejeição de produção.
- Congelar CST em enum Python sem tabela versionada.

---

## 14. Recomendações à direção (decisões pedidas)

| # | Decisão | Opções | Recomendação |
|---|---------|--------|--------------|
| D1 | Escopo 2026 | Só NFS-e RTC **vs** NFS-e+NF-e | **NFS-e RTC P0**; NF-e só se houver receita de venda de produto em 2026 |
| D2 | Locação | H1 / H2 / H3 | Parecer contábil em 15 dias; senão **não desenvolver** |
| D3 | Contábil MVP | E-mail XML **vs** portal | E-mail/lote P1; portal P2 |
| D4 | Provider | Focus continua **vs** SEFAZ direto | **Focus** (alinhado arquitetura atual) |
| D5 | Orçamento programa RTC | Sprint avulsa **vs** programa 2026–27 | **Programa** com owner compliance |
| D6 | SN híbrido | Forçar um modo **vs** configurar por tenant | Configurável + alerta prazo set/2026 |

---

## 15. Changelog deste estudo

| Versão | Data | Notas |
|--------|------|-------|
| 0.1.0-draft | 2026-07-26 | Primeira consolidação: EC 132, LC 214, LC 227, NT 2025.002 (NF-e), NT 009 NFS-e, cronograma 2026–2033, gaps Hub, matriz MoSCoW, contábil, locação, split |

### Fontes consultadas (amostra)

- Planalto — LC 214/2025.
- Portal Nacional NF-e — NT 2025.002-RTC (versões até v1.50, jun/2026).
- Portal NFS-e — NT SE/CGNFS-e 009 (04/06/2026) e anexos VI/VII.
- ADCT/EC 132 — calendário transição (síntese cruzada com material técnico de mercado verificado em 2026).
- Docs internos: `Exeq_Hub_NFSe_Emission_Architecture_Reference.md` (NF-e produto fora do DoD atual).

---

## 16. Próximos artefatos (após aprovação da direção)

1. **ADR-001** — Programa RTC no Hub (escopo D1–D6).
2. **ADR-002** — Modelo `FiscalDocument` vs extensão `NfIssue`.
3. **Patch v3.1** — entidades classificação + snapshot IBS/CBS.
4. **Patch v1** — requisitos funcionais RTC e contábil.
5. **Plano de testes E2E RTC** (espelho do plano Admin atual).
6. **Spike Focus** — campos IBS/CBS em `/v2/nfsen` e `/v2/nfe`.

---

*Fim do estudo 0.1.0-draft. Documento vivo: atualizar a cada NT material.*
