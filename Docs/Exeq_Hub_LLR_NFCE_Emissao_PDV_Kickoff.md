# EXEQ Hub — LLR NFC-e (modelo 65) · Emissão PDV / Balcão — Kickoff de implementação

| Campo | Valor |
|-------|-------|
| Status | **Proposta para aprovação PO** (início de implementação) |
| Versão | **0.1.0-draft** |
| Data | 2026-09-04 |
| Tipo | LLR de produto + arquitetura (kickoff fábrica) |
| Relaciona | `ADR_NFE_001` · `ADR_RTC_001` · `Exeq_Hub_Reforma_Tributaria_RTC_MultiDocumento_Estudo_Tecnico.md` · `DISCOVERY_IFOOD_FISCAL_B.md` |
| UF pivot | **SP (São Paulo)** — onda 1 |
| Escopo onda 1 | NFC-e **saída presencial** (balcão/PDV); integração com decisão CPF/CNPJ; **Simples Nacional + Regime Normal** no emitente |

---

## 0. Sumário executivo

O EXEQ Hub possui **NF-e modelo 55 B2B** implementada (`apps/nfe/`, `integrations/sefaz_nfe/`). **NFC-e modelo 65 não existe** no repositório (confirmado em código e em `DISCOVERY_IFOOD_FISCAL_B.md`).

Este documento consolida a análise do time sênior e define **regras, arquitetura, fases e gates** para iniciar a implementação da NFC-e como emissor próprio SEFAZ, reutilizando certificado A1, transporte e padrões já validados na NF-e, **sem duplicar motor fiscal nem contaminar NFS-e**.

**Decisões de produto PO (entrada deste LLR):**

1. **Sem CPF/CNPJ** → NFC-e 65 (consumidor não identificado, quando permitido).
2. **CPF informado** → NFC-e 65 com identificação no XML.
3. **CNPJ informado** → **NF-e 55** (política EXEQ; ver §4.2 — diverge da permissão legal pós-SINIEF 12/2026).
4. Emitente **Simples Nacional**: alíquotas ICMS/PIS/COFINS **zeradas** são válidas quando CSOSN/CST assim determinam; **NCM + CFOP + CSOSN** são obrigatórios por item.

---

## 1. Fontes normativas (versionar no cofre de conformidade)

| Fonte | URL / referência | Uso no Hub |
|-------|------------------|------------|
| **NT 2025.002-RTC** (NF-e/NFC-e) | [Portal Nacional NF-e](https://www.nfe.fazenda.gov.br/portal/principal.aspx) → Documentos | Layout XML mod 65, Grupo UB (IBS/CBS/IS), W03, RVs |
| **Informe Técnico 2025.002** (ex. v1.60) | Idem → Diversos | Tabelas CST, cClassTrib, crédito presumido |
| **LC 214/2025** | Planalto | IVA dual, transição 2026–2033 |
| **Ajuste SINIEF 12/2026** | CONFAZ | Revoga proibição NFC-e com CNPJ consumidor final |
| **Portaria CAT 12/SP** | SEFAZ-SP | Identificação destinatário, limites, DANFE-NFC-e |
| **Manual NFC-e / NFe 4.00** | Portal NF-e + manual UF | CSC, QR Code, contingência |
| Estudo interno RTC | `Exeq_Hub_Reforma_Tributaria_RTC_MultiDocumento_Estudo_Tecnico.md` §5.1 | Roadmap IBS/CBS paralelo |

**Governança:** criar/atualizar registro em `RtcNormativeVersion` (já existente para NFS-e) incluindo refs NT 2025.002 para **mercadoria mod 65**.

---

## 2. Estado atual do codebase (diagnóstico)

| Capacidade | Status | Local principal |
|------------|--------|-----------------|
| NF-e 55 emit | ✅ | `apps/nfe/services.py` → `emit_invoice` |
| XML mod 55 | ✅ | `integrations/sefaz_nfe/xml_nfe.py` (`<mod>55</mod>` fixo) |
| DANFE NF-e A4 | ✅ | `integrations/sefaz_nfe/danfe/` |
| Motor ICMS SN (CSOSN, alíq. zero) | ✅ | `apps/nfe/tax.py` |
| Validação NCM / CFOP | ✅ | `apps/nfe/tax.py` → `build_validation` |
| Customer CPF/CNPJ | ✅ | `master_data.Customer` + `shared/validators.py` |
| NFC-e mod 65 | ❌ | — |
| CSC / QR / infNFeSupl | ❌ | — |
| DANFE NFC-e (cupom) | ❌ | — |
| Seleção NFC-e ↔ NF-e | ❌ | — |
| Contingência SAT/EPEC SP | ❌ | `tpEmis=1` fixo |
| Food PDV fiscal | ❌ | `FoodOrder` sem emissão DF-e |
| RTC IBS/CBS no XML mod 55/65 | ❌ | placeholder `taxes.rtc` |

**Reuso direto:** `integrations/sefaz_nfe/port.py`, `sign.py`, `transport.py`, `endpoints.py`, `access_key.py` (parâmetro `model`), `DigitalCertificate`, `NfeNumberSeries` (ou série dedicada mod 65), padrão FSM/outbox/artifacts.

---

## 3. Regras de negócio — identificação do consumidor

### 3.1 Matriz PO (política EXEQ)

| Identificação | Documento | Cadastro cliente | Observação UX |
|---------------|-----------|------------------|---------------|
| Nenhuma | **NFC-e 65** | Não exigido | Botão “Continuar sem identificação” |
| CPF válido | **NFC-e 65** | Não exigido (snapshot na venda) | CPF no XML `<dest><CPF>` |
| CNPJ válido | **NF-e 55** | Wizard NF-e (endereço, IE dest.) | Aviso: *“CNPJ exige NF-e modelo 55”* |

**Ambiguidade:** se CPF **e** CNPJ informados → **bloquear** emissão; mensagem clara.

### 3.2 Regras fiscais SP / nacional (validação SEFAZ — não simplificar)

Parâmetros default nacional (SEFAZ pode alterar por UF — **confirmar em homolog SP**):

| Situação | Regra |
|----------|-------|
| Destinatário **não identificado** | Permitido se valor **&lt; limite UF** (default **R$ 10.000,00**) |
| Valor **≥ R$ 10.000,00** | Obrigatório CPF, CNPJ ou doc estrangeiro (rejeição **750** típica) |
| **Entrega em domicílio** (SP CAT 12) | CPF/CNPJ + **endereço** |
| **Venda a prazo** (SP) | CPF/CNPJ + informações em `infAdFisco` |
| Comprador **solicita** identificação | CPF/CNPJ mesmo abaixo do limite |
| Valor **≥ R$ 200.000** identificado | Exige **NF-e**, não NFC-e |

Implementar via **`FiscalDocumentPolicy`** parametrizável por UF — **sem** `if uf == "SP"` espalhado.

### 3.3 Política CNPJ → NF-e vs norma 2026

| | Legislação (pós-SINIEF 12/2026) | Política EXEQ (PO) |
|--|--------------------------------|---------------------|
| CNPJ consumidor final | NFC-e **permitida** | **Proibida** — forçar NF-e 55 |
| CNPJ operação B2B | NF-e 55 | NF-e 55 ✓ |

Documentar na UI que a rota CNPJ→NF-e é **decisão comercial EXEQ**, não requisito universal da SEFAZ.

---

## 4. Regras fiscais — emitente e itens

### 4.1 Cabeçalho NFC-e (mod 65)

| Campo XML | Valor típico PDV | Hub NF-e hoje |
|-----------|------------------|---------------|
| `mod` | **65** | 55 |
| `tpImp` | **4** (NFC-e) | 1 |
| `indFinal` | **1** | default 0 |
| `indPres` | **1** (presencial) | default 9 |
| `idDest` | **1** (interna) | ok |
| `CRT` | 1 (SN) ou 3 (Normal) | ok via `Provider.tax_regime` |
| `finNFe` | 1 | ok |

### 4.2 Simples Nacional (CRT = 1)

| Campo item | Obrigatório | Comportamento |
|------------|-------------|---------------|
| **NCM** | Sim (8 dígitos) | Validar em `build_validation` |
| **CFOP** | Sim (4 dígitos) | Varejo interno: **5102** default; validar 5xxx×UF |
| **CSOSN** | Sim (3 dígitos) | Default **102**; **validar presença** (não só default silencioso) |
| **orig** | Sim | Default `0` |
| **pICMS / vICMS** | — | **Zero ou ausente** para CSOSN 102/103/400/500 — **correto** |
| **PIS/COFINS** | — | CST **07** (não tributado), valor 0 — padrão SN integrado |

**Gap código atual:** XML usa **somente** grupo `ICMSSN102`. CSOSN ≠ 102 exige mapeamento para `ICMSSN101`, `ICMSSN500`, etc. (**Must** na NFC-e).

### 4.3 Regime Normal (CRT = 3) — NFC-e raro no PDV

Se emitente Presumido/Real operar PDV: ICMS **CST 00** (ou outro), PIS/COFINS conforme produto. Mesma validação NCM/CFOP. Preferir NF-e se destinatário CNPJ (política PO).

### 4.4 Destinatário no XML NFC-e

| Modo | Grupo `<dest>` |
|------|----------------|
| Não identificado | **Omitir** `<dest>` (ou regra NT vigente) |
| CPF | `<CPF>` + `xNome` (homolog: texto fixo SEFAZ) |
| CNPJ | **Não aplicar** na NFC-e (redirecionar NF-e) |

---

## 5. Reforma Tributária (IBS/CBS/IS) — NFC-e

Referência: **NT 2025.002-RTC** (mesma família NF-e/NFC-e).

| Marco | CRT=3 (Normal) | CRT=1 (Simples) |
|-------|----------------|-----------------|
| Ano-teste 2026 | Destaque informativo CBS 0,9% + IBS 0,1% | Idem (apuração informativa) |
| **Homolog com UB** | jul/2026 | — |
| **Produção obrigatório UB** | **03/08/2026** | **04/01/2027** |
| Grupo XML | `det/imposto/UB` + totais **W03** / `vNFTot` | + `gTribSN` quando aplicável |

**Onda 1 NFC-e (este LLR):** implementar motor legado (ICMS/PIS/COFINS) + **hook RTC** (`taxes.rtc`) em shadow; **Grupo UB** em fase **NFCE-R2** paralela ao programa NF-e (`NFE-R01…R10` do estudo RTC).

**DANFE NFC-e:** NT de **layout de impressão** IBS/CBS ainda **em estudo SEFAZ** — priorizar **XML autorizado**; PDF cupom pode usar layout interno até NT publicar campos RTC na impressão.

Reutilizar: `apps/fiscal/rtc_classification.py`, `RtcNormativeVersion` — **não** reutilizar fórmula BC de serviço (`rtc_assessment.py`) para mercadoria.

---

## 6. Arquitetura proposta

### 6.1 Camadas (View → Service → Domain → Integration)

```
Hub PDV UI (balcão / Food counter)
    ↓
SaleCheckoutService
    ↓
apps/fiscal/document_policy/engine.py   ← resolve_document_route()
    ↓
┌─────────────────────┬──────────────────────┐
│ apps/nfce/services  │ apps/nfe/services    │
│ emit_nfce()         │ emit_invoice()         │
└─────────┬───────────┴──────────┬───────────┘
          ↓                      ↓
integrations/sefaz_nfe/
  xml_nfce.py (mod 65)     xml_nfe.py (mod 55)
  nfce_supplement.py       danfe/ (existente)
  port.py · sign · transport (compartilhados)
```

### 6.2 Módulos novos / alterados

| Módulo | Ação |
|--------|------|
| `apps/fiscal/document_policy/` | **Novo** — registry UF, engine, tipos |
| `apps/nfce/` | **Novo** — models, services, tax adapter, URLs |
| `integrations/sefaz_nfe/xml_nfce.py` | **Novo** — builder mod 65 |
| `integrations/sefaz_nfe/nfce_supplement.py` | **Novo** — CSC, QR, `infNFeSupl` |
| `integrations/sefaz_nfe/danfe_nfce/` | **Novo** — PDF cupom + QR |
| `integrations/sefaz_nfe/xml_nfe.py` | **Alterar** — extrair helpers comuns; mapear CSOSN→grupo XML |
| `apps/nfe/tax.py` | **Alterar** — validação CSOSN SN; `map_csosn_to_xml_group()` |
| `apps/hub_v4/` | **Novo** views/templates PDV ou extensão Food |
| `config/settings.py` | **Alterar** — `NFCE_ENABLED`, `NFCE_CSC_*`, `NFCE_DEFAULT_UF_POLICY` |

### 6.3 Multi-tenant

- Policy por **`provider.address.uf`** + overrides em `tenant.settings.pdv_policy`.
- Feature flags: `NFCE_ENABLED` global + `nfce_enabled` no tenant (espelhar `nfe_enabled`).
- Certificado: mesmo `DigitalCertificate` A1 do CNPJ (`ADR_NFE-001`).
- Numeração: série **dedicada mod 65** (`NfceNumberSeries` ou campo `model` em `NfeNumberSeries`).

### 6.4 DER (amend v3.1 — antes do 1º PR de models)

| Entidade | Campos principais |
|----------|-------------------|
| `NfceInvoice` | tenant, provider, status FSM, series, number, tp_amb, total_cents, identification_snapshot JSON, fiscal_snapshot, access_key |
| `NfceInvoiceItem` | ncm, cfop, csosn, origin, taxes JSON |
| `NfceProduct` | reutilizar `NfeProduct` com flag ou tabela irmã — **decisão fábrica:** estender `NfeProduct` com `channels` (b2b/pdv) para evitar duplicata SKU |
| `TenantCscToken` | csc_id, csc_token_encrypted, tp_amb, provider (opcional) |

### 6.5 Contingência SP

SAT/EPEC: **fora da onda 1** (complexidade alta). Documentar limitação: em indisponibilidade SEFAZ, PDV pode operar sem cupom ou em modo offline manual — **não** simular autorização.

---

## 7. UX — tela PDV (proposta)

```
[ Carrinho · pagamento ]

Identificação do consumidor (opcional):
  CPF  [_______________]
  CNPJ [_______________]  → se preenchido: banner “Será emitida NF-e modelo 55”
  [ Continuar sem identificação ]

[ Emitir documento fiscal ]
```

- **Não** exigir cadastro de cliente para NFC-e.
- CPF/CNPJ validados client-side + server-side (`validate_cpf` / `validate_cnpj`).
- SN: não editar alíquota no PDV; mostrar CSOSN/CFOP/NCM do produto (somente leitura).

---

## 8. Fases de entrega (MoSCoW)

### Fase NFCE-0 — Fundação (Must)

| ID | Entrega | DoD |
|----|---------|-----|
| NFCE-0.1 | ADR/LLR aprovado PO | Este documento |
| NFCE-0.2 | `document_policy` + testes T1–T10 | Unitários verdes |
| NFCE-0.3 | Amend DER + models `NfceInvoice*` | Migration review |
| NFCE-0.4 | Feature flags `NFCE_ENABLED` | Default off |

### Fase NFCE-1 — Core emissão SP homolog (Must)

| ID | Entrega | DoD |
|----|---------|-----|
| NFCE-1.1 | `xml_nfce.py` + CSC/QR homolog | Golden-file XSD |
| NFCE-1.2 | `emit_nfce()` FSM (stub + http) | Paridade NF-e |
| NFCE-1.3 | Identificação: anon / CPF / bloqueio CNPJ→NF-e | Testes integração |
| NFCE-1.4 | SN: NCM+CFOP+CSOSN validados; ICMS zerado ok | Testes T-SN-1…6 |
| NFCE-1.5 | CSOSN → grupo XML dinâmico | ≠102 coberto |
| NFCE-1.6 | UI PDV mínima Hub ou Food `counter` | Smoke manual PO |

### Fase NFCE-2 — RTC + produção (Must antes prod)

| ID | Entrega | DoD |
|----|---------|-----|
| NFCE-2.1 | Grupo UB + W03 (mod 65) shadow/emit | Gate por data+CRT |
| NFCE-2.2 | Credenciamento CSC produção SP | Ops runbook |
| NFCE-2.3 | DANFE NFC-e cupom (layout interno + QR) | Download PDF |
| NFCE-2.4 | Gate G-EMIT-NFCE homolog | Evidência JSON |

### Fase NFCE-3 — Escala (Should)

| ID | Entrega |
|----|---------|
| NFCE-3.1 | Multi-UF policy registry |
| NFCE-3.2 | Integração iFood lote (parceiro ou nativo) |
| NFCE-3.3 | Contingência SAT (spike) |

---

## 9. Gates e feature flags

| Flag | Default | Efeito |
|------|---------|--------|
| `NFCE_ENABLED` | `false` | Módulo global |
| `tenant.settings.nfce_enabled` | `false` | Opt-in tenant |
| `NFCE_HTTP_MODE` | `stub` | stub / http |
| `NFCE_RTC_MODE` | `shadow` | off / shadow / emit |
| `NFCE_UF_POLICY` | `sp_v2026` | Registry de regras |

**G-EMIT-NFCE:** autorização homolog SP + XML + DANFE cupom + CSC válido — espelhar checklist `nfe_g_emit_checklist.py`.

---

## 10. Plano de testes (mínimo)

| ID | Cenário |
|----|---------|
| T1 | Sem ID, R$ 100, SP → NFC-e sem `<dest>` |
| T2 | CPF válido → NFC-e com `<CPF>` |
| T3 | CNPJ válido → rota NF-e, **não** chama `emit_nfce` |
| T4 | CPF inválido → bloqueio |
| T5 | CNPJ inválido → bloqueio |
| T6 | CPF + CNPJ → bloqueio ambiguidade |
| T7 | Sem ID, R$ 9.999 → OK |
| T8 | Sem ID, R$ 10.000 → bloqueio (identificação) |
| T8b | Sem ID + entrega → bloqueio |
| T9 | UF SP → policy SP |
| T10 | UF RJ → policy default nacional |
| T-SN-1 | SN CSOSN 102, alíq. zero → XML válido |
| T-SN-2 | SN sem CSOSN → bloqueio |
| T-SN-3 | SN sem NCM → bloqueio |

Local: `apps/fiscal/tests/test_document_policy.py`, `apps/nfce/tests/`, `integrations/sefaz_nfe/tests/test_xml_nfce.py`.

---

## 11. Riscos e pendências normativas

| # | Risco / pendência | Mitigação |
|---|-------------------|-----------|
| P1 | Premissa “NFC-e pronta” incorreta | Greenfield controlado; este LLR |
| P2 | Limite R$ 10.000 SP — confirmar parâmetro UF | Homolog + tabela RV |
| P3 | CNPJ→NF-e vs SINIEF 12/2026 | Política EXEQ documentada |
| P4 | CSOSN só ICMSSN102 | NFCE-1.5 |
| P5 | RTC jan/2027 SN vs ago/2026 Normal | Flags por CRT+data |
| P6 | SAT SP contingência | Fora onda 1; runbook manual |
| P7 | DANFE RTC sem NT impressão | XML first; PDF informativo |
| P8 | Regressão NF-e B2B | Bounded context; policy antes do emit |

---

## 12. Fora de escopo (onda 1)

- NFC-e interestadual / entrega complexa
- Inutilização UI NFC-e (reutilizar padrão NF-e depois)
- Estoque / WMS
- Split payment
- MEI dispensas automáticas (validar caso a caso)
- CT-e / MDF-e

---

## 13. Aprovação PO (checklist)

- [ ] Aprovar matriz CPF/CNPJ (§3.1) incluindo CNPJ→NF-e como política EXEQ
- [ ] Aprovar UF pivot SP e fases NFCE-0…2
- [ ] Autorizar amend DER §6.4
- [ ] Autorizar início **Fase NFCE-0** (policy + DER) sem SEFAZ prod
- [ ] Definir tenant piloto + CSC homolog SP

---

## 14. Referência cruzada — o que muda vs hoje

| Hoje | Após implementação |
|------|---------------------|
| Só NF-e 55 B2B | NFC-e 65 PDV + rota CNPJ→NF-e |
| Destinatário sempre cadastrado | Identificação opcional/transitória na venda |
| Sem PDV fiscal | Balcão emite cupom |
| CSOSN default silencioso | CSOSN validado; grupos XML corretos |
| Sem RTC no XML produto | Shadow → emit conforme cronograma NT |

---

*Documento preparado pelo time sênior EXEQ Hub para kickoff de implementação. Alterações normativas posteriores à NT 2025.002 devem gerar nova versão deste LLR e entrada em `RtcNormativeVersion`.*
