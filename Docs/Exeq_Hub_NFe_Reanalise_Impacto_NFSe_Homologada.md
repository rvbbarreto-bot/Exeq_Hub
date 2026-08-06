# EXEQ Hub — Reanálise de impacto: NF-e (produto) sobre a base NFS-e homologada

| Campo | Valor |
|-------|--------|
| Tipo | **Estudo técnico de impacto + reavaliação** (não implementação) |
| Versão | **1.0.0** |
| Data | 2026-08-05 |
| Status | **Base para LLR NF-e v0.2** |
| Premissa PO | Não há NF-e de produto em banco; **sem risco de multa por alteração de notas retroativas de produto** no estado atual |
| Escopo NF-e (PO) | B2B modelo 55; **UF pivot SP**; até 10 UFs no multi; SN + Normal; emissor EXEQ SEFAZ; **sem estoque** |
| Base homologada | Emissor próprio **NFS-e Nacional** (ADR-NFSE-001, LLR NFS-e 0.3, plano M5) |
| Relaciona | `Exeq_Hub_LLR_NFe_UI_B2B_Sem_Estoque.md` **v0.2**; revisão comitê 2026-08-05 recalibrada |

---

## 0. Correção de premissa da revisão comitê (2026-08-05)

### 0.1 O que muda com “zero NF-e no banco”

| Afirmação anterior (comitê) | Releitura com premissa PO |
|-----------------------------|---------------------------|
| Snapshot frágil gera **multa por alterar notas retroativas** | **Não há** emissão de produto persistida: **não existe** estoque de NF-e a corromper hoje |
| Migrar schema de nota produto sob dados vivos | **Greenfield**: modelo de domínio NF-e pode nascer limpo |
| Retrabalho de dados históricos produto | **Zero** para produto até o go-live NF-e |

### 0.2 O que **não** muda

| Tema | Por quê continua Must |
|------|------------------------|
| Snapshot **desde a 1ª nota autorizada** | A partir do piloto, toda nota autorizada é legal; design barato agora |
| Isolamento multi-tenant / IDOR / cert | Já production concern do Hub (NFS-e + multi-CNPJ) |
| Numeração SEFAZ (série/nNF) | Existe no momento da 1ª reserva em homolog/prod — falha gera furo/rejeição **mesmo sem histórico** |
| Não quebrar **NFS-e** | Há (ou haverá) notas de **serviço** e infraestrutura compartilhada em uso |
| Multi-UF / motor ICMS / SEFAZ | Complexidade de **produto novo**, não de migração |

**Conclusão:** gravidade de **migração de dados retroativos de NF-e** cai de **Crítica → N/A (hoje)**.  
Gravidade de **design incorreto de imutabilidade pós-autorização** permanece **Alta** (adiável em migração zero, **não** adiável no desenho).

---

## 1. O que já está homologado / maturo na NFS-e (inventário reutilizável)

Fonte: código `apps/issuance`, `integrations/nfse`, `apps/accounts`, `apps/fiscal`, docs ADR/LLR/plano emissor próprio.

### 1.1 Plataforma (reuso alto)

| Capacidade | Onde | Reuso para NF-e |
|------------|------|-----------------|
| Multi-tenant + Provider (emitente CNPJ) | `master_data.Provider`, tenancy | **Alto** — emitente; completar IE se faltar |
| Customer (destinatário) | `master_data.Customer` | **Alto** — enriquecer IE/endereço/IBGE |
| Certificado A1 + multi-CNPJ | `DigitalCertificate`, onboarding | **Alto** — mesmo ativo mTLS/assinatura |
| FSM de documento fiscal | `NfIssue.Status` + services | **Padrão** — copiar espírito, **não** a tabela 1:1 |
| Idempotência tenant+key | constraint `uq_nf_issue_tenant_idempotency` | **Alto** |
| Correlation / events | `NfIssueEvent`, `correlation_id` | **Alto** |
| Snapshot fiscal (padrão) | `FiscalRuleSnapshot` + `resolved_params` | **Padrão** — espelhar em domínio mercadoria |
| Artefatos XML/PDF + checksum | `NfArtifact` + `StoredFile` + `ensure_authorized_artifacts` | **Alto** (kinds/DANFE ≠ DANFSe) |
| XMLDSig + material PFX | `integrations/nfse/xmldsig.py`, mTLS SEFIN | **Padrão assinar** — **schema/XPath diferentes** |
| mTLS com contexto PFX | `sefin_mtls` | **Alto** para SEFAZ HTTPS/client cert se aplicável |
| Worker Celery emit/poll | `process_nf_issue`, `poll_nf_issue` | **Alto** |
| Outbox / canal pós-autorizada | ops dispatcher, WhatsApp mídia | **Alto** (event kind novo) |
| Poll só recuperação | LLR RF-15/20 | **Conceito** — SEFAZ muitas vezes async; adaptar |
| Admin emission + gates security | Admin, G-SEC patterns | **Parcial** |
| Porta de provider | `NfseProvider` Protocol | **Padrão de porta** → nova `NfeProvider` |
| Foco lab preservado | Focus Nfse code | **Não confundir** com Focus NF-e produto |

### 1.2 Domínio NFS-e (reuso baixo / zero no núcleo fiscal)

| Capacidade | Por quê **não** reusar direto |
|------------|-------------------------------|
| `ServiceCatalogItem` / LC116 / código nacional ISS | Mercadoria usa NCM/CFOP |
| `MunicipalTaxRule` / ISS | Motor ICMS/PIS/COFINS |
| Mapper DPS / SEFIN Nacional | Autoridade SEFAZ UF + XML NF-e 4.00 |
| DANFSe NT 008 | DANFE (layout distinto) |
| Gate IBGE “município aderente AO nacional de **serviço**” | UF emitente + SEFAZ mercadoria |
| Campos UI/API `amount_cents` monoline serviço | Multi-item, frete, pagamentos tPag |

### 1.3 Padrão arquitetural already-locked (copiar, não reinventar)

Do plano NFS-e §4.1 e v2:

```text
View → Serializer → Application Service → Domain → ORM
integrations/* = único lugar de HTTP autoridade
Fiscal resolve → snapshot → builder XML → sign → adapter → FSM → artifacts → outbox
```

**Proibido (já no acordo de engenharia):** Onion full, misturar View com XML SEFAZ, hard delete de autorizada.

---

## 2. Matriz de impacto do desenvolvimento NF-e

### 2.1 Impacto em código / módulos existentes

| Área | Tipo de impacto | Risco se mal feito | Mitigação |
|------|-----------------|--------------------|-----------|
| `apps/issuance` | Extensão ou módulo irmão | Contaminar `NfIssue` com campos ICMS | **Bounded context** `nfe` **ou** `document_kind` + tabelas irmãs; **não** colunas ISS+ICMS na mesma linha de serviço |
| `apps/fiscal` | Novo subdomínio mercadoria | Motor monólito ISS+ICMS | Pacote/tax engine mercadoria separado; reutilizar só versionamento de catálogo |
| `integrations/` | Novo pacote `sefaz_nfe` | Misturar com `nfse/` | Pasta distinta + porta distinta |
| `DigitalCertificate` | Compartilhado | Fila SEFIN e SEFAZ no mesmo cert | OK se CNPJ correto; ops de expiração já útil |
| `Customer` / `Provider` | Migrations additive | Quebra forms NFS-e | Campos opcionais / defaults; badge “apto NF-e” |
| Celery / Redis / outbox | Novas tasks | Starvation se volume alto | Filas nomeadas ou prioridade (fase 2) |
| Frontend shell | Novas rotas T0–T8 | Nav poluída | Item “NF-e” separado de “NFS-e” (UX foundations) |
| WhatsApp engine | Opção futura artefato | Misturar fluxos emissão | Só após `nfe.authorized` event |
| Derivados DER v3.1 | Amend necessário | Doc desatualizado | ADR + amend DER **antes** de merge de models |

### 2.2 Impacto operacional / homologação

| Tema | NFS-e hoje | NF-e acrescenta |
|------|-----------|-----------------|
| Autoridade | SEFIN/ADN (um “país”) | Até **10 SEFAZ** (PO) |
| Credenciamento | Município aderente + cert | IE + credenciamento UF + serie |
| Homolog | 1 pipeline mTLS bem conhecido | Matriz UF × ambiente |
| Risco de piloto | Controlado (serviço) | Novo produto — **não** reutiliza G-EMIT de serviço |

### 2.3 Impacto em dados existentes

| Dataset | Impacto |
|---------|---------|
| NF-e produto | **Nenhum** (vazio) |
| NFS-e / artefatos serviço | **Não migrar**; não reescrever IDs |
| Certificates / tenants | Compartilhados; só uso cruzado |
| Service catalog | Intact |

---

## 3. O que a NFS-e homologada **prove** e o que ela **não** prova

| Capacidade | Prova NFS-e | Gap para NF-e |
|------------|-------------|---------------|
| Assinar XML com A1 e enviar a governo | **Sim (DPS)** | XML 55 + regras SEFAZ |
| mTLS + gestão de cert multi-CNPJ | **Sim** | Endpoints e cadeia por UF |
| FSM draft→…→authorized/cancel | **Sim** | Número série; denegação; contingência |
| Snapshot + artifacts idempotentes | **Sim (padrão)** | Snapshot multi-item ICMS |
| UI async poll / Admin | **Parcial (NFS-e)** | Telas produto/itens (LLR UI) |
| Motor ISS multi-regime | **Parcial SN/ISS** | CST/CSOSN ICMS + PIS/COFINS |
| 10 UFs no dia 1 | **N/A** (nacional serviço) | Projeto multi-UF novo |

**Tradução para estimativa:**  
~40–55% do **esforço de plataforma/emissão genérica** já pago.  
~0% do **motor SEFAZ 55 multi-UF** já pago.  
~20–30% do **padrão UI de emissão** (lista/detalhe/cancel) reaproveitável com adaptação.

---

## 4. Recalibração da aprovação de arquitetura

| Critério comitê anterior | Nota recalibrada | Motivo |
|--------------------------|------------------|--------|
| Risco multa dados retroativos NF-e | **N/A → mitigado** | Banco sem NF-e produto |
| Necessidade de LLR domínio | **Mantém P0** | Greenfield **não** desobriga desenho |
| Bloquear 100% UI até domínio | **Relaxa** | G-UI-WIRE e G-UI-MVP **stub** liberados sobre LLR UI v0.2 |
| Desenvolver SEFAZ/emit real | **Ainda exige** ADR/LLR domínio + OpenAPI | Mesmo greenfield |
| Parecer global | De “só revisão bloqueante” → **Aprovado com ressalvas** para trilhas paralelas (ver §7) |

---

## 5. Estratégia de implementação recomendada (impacto mínimo na NFS-e)

### 5.1 Princípio: “irmão, não herdeiro frágil”

```text
                    ┌─────────────────────────────┐
                    │  Shared platform            │
                    │  tenancy, cert, outbox,     │
                    │  storage, workers shell     │
                    └───────────┬─────────────────┘
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
     apps/issuance (NFS-e)              apps/nfe  (ou issuance/nfe)
     NfIssue + SEFIN + ISS              NfeInvoice + SEFAZ + ICMS
     integrations/nfse/*                integrations/sefaz_nfe/*
```

- **Fábrica:** proibir PR que altere mapper DPS/SEFIN “de passagem” para caber NF-e.  
- Migrations **additive** em `Customer`/`Provider`.  
- Feature flags: `NFE_ENABLED` (default off) até G-EMIT-NFE.

### 5.2 Ondas (alinha PO + reuso)

| Onda | Conteúdo | Depende de NFS-e? |
|------|----------|-------------------|
| **U0** | ADR + LLR domínio greenfield + OpenAPI draft | Docs apenas |
| **U1** | UI T0/T4/T5/T6 + produtos (API stub) | Nenhum runtime SEFAZ |
| **U2** | Domain NFe + series + snapshot + FSM (1 UF lab) | Cert + worker pattern |
| **U3** | SEFAZ adapter 1 UF + DANFE min + cancel | XMLDSig pattern |
| **U4** | 10 UFs config + QA matrix | Ops |
| **U5** | Motor Normal depth + RTC hooks | Fiscal tables |

### 5.3 Numeração (greenfield-friendly)

Como não há histórico:

- Pode escolher **EXEQ controla série/nNF** desde o dia 1 (lock `NumberSeries`).  
- Não precisa migração de furos legados.  
- Ainda **Must** travar política reserva/consumo (senão furo **na 1ª semana** de piloto).

### 5.4 Snapshot (greenfield-friendly)

- Não há custo de backfill.  
- Implementar **imutabilidade no submit** (copiar item/partes) no 1º PR de domínio — custo marginal baixo, evita dívida futura.  
- Comitê: reclassificar de “crise de multa retroativa” para **“padrão de qualidade fiscal dia-1”**.

---

## 6. Risco residual (ordenado)

| ID | Risco | Gravidade recalibrada | Notas |
|----|-------|---------------------|-------|
| R1 | Contaminar path/código NFS-e | **Alta** | Principal risco real **hoje** |
| R2 | FSM/número sem política no 1º emit | **Alta** | Independent de histórico |
| R3 | Design snapshot frouxo até 1ª prod | **Média→Alta** | Sem multa ontem; multa **a partir do piloto** |
| R4 | 10 UFs day-1 | **Alta** (escopo/calendar) | Inalterado |
| R5 | Motor SN+Normal subestimado | **Alta** | Inalterado |
| R6 | API/UI sem contrato | **Média** | UI stub liberado; emit real bloqueado |
| R7 | Multa por editar notas produto antigas | **N/A** | Zero registros produto |
| R8 | Reforma tributária rigid UI | **Média** | Design `taxes{}` extensível cedo |

---

## 7. Parecer de aprovação (pós-reanálise)

### **Aprovado com ressalvas**

| Trilha | Liberado? | Ressalvas |
|--------|-----------|-----------|
| UI protótipo / mock (G-UI-WIRE, G-UI-MVP stub) | **Sim** | Seguir LLR UI **v0.2**; não persistir “NF-e fake authorized” em prod |
| Domínio + OpenAPI + NumberSeries | **Sim, em paralelo** | LLR domínio greenfield (próximo artefato) |
| Adapter SEFAZ multi-UF emit real | **Após** U0/U2 mínimo 1 UF | Não copiar `NfIssue` de serviço |
| Go-live multi-tenant produto | **Após** G-EMIT-NFE + G-UI-MVP real | Snapshot imutável obrigatório |

Justificativa: premissa de **greenfield de produto** remove o pânico de migração; a plataforma NFS-e **homologada** reduz risco de inventar “emissor do zero”; os gaps SEFAZ/ICMS/10 UF permanecem reais e fora do LLR UI sozinho.

---

## 8. Artefatos derivados

| Artefato | Versão | Papel |
|----------|--------|--------|
| Este estudo | 1.0.0 | Impacto + reuso + parecer |
| `Exeq_Hub_LLR_NFe_UI_B2B_Sem_Estoque.md` | **0.2.0** | UI recalibrada |
| `ADR_NFE_001_Emissor_Proprio_SEFAZ.md` | **Aprovado** (PO 2026-08-05) | Decisão emissor EXEQ SEFAZ 55 |
| `Exeq_Hub_LLR_NFe_Dominio_SEFAZ_Greenfield.md` | **0.1.0** | Domínio/FSM/número/tax/SEFAZ |
| Próximo (recomendado) | — | OpenAPI NFe v1 + lista 10 UFs (U0) |

---

## 9. Histórico

| Versão | Data | Nota |
|--------|------|------|
| 1.0.0 | 2026-08-05 | Reanálise: greenfield NF-e; inventário NFS-e homologada; recalibração riscos/aprovação |
