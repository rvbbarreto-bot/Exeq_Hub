# Roteiro de teste E2E — Emissão NFS-e via Django Admin

**Produto:** EXEQ Hub  
**Escopo:** cadastro da empresa → certificado → regra fiscal → emissão → poll → (opcional) cancelamento  
**UI:** Django Admin (`/admin/`) — Sprint 7 antecipada (QA)

---

## Ambiente

| Item | Valor |
|------|--------|
| URL Admin | http://127.0.0.1:8000/admin/ |
| Login QA (exemplo) | `qa@exeq.local` / `ExeqQa123!` |
| Pré-requisito `.env` | `FOCUS_HTTP_MODE=http`, `FOCUS_API_TOKEN` e `FOCUS_API_BASE_URL` válidos |

**Nota importante:** a emissão Focus autentica com **token Focus** (`.env` / secret), não com o PFX no Admin. O certificado no Hub é cadastro/gate (ex.: DAS). Inclua-o no roteiro como passo de configuração da empresa; a autorização da NFS-e depende do Focus + dados fiscais.

---

## 0. Smoke do ambiente

| # | Ação | Resultado esperado | OK? |
|---|------|--------------------|-----|
| 0.1 | Abrir `/admin/` e logar | Header **EXEQ Hub — Admin QA** | ☐ |
| 0.2 | Confirmar `.env` com Focus HTTP | Token válido (sem 401 no Focus) | ☐ |

---

## 1. Empresa (Tenant)

**Accounts → Tenants → Add**

| Campo | Valor sugerido (Atibaia QA) |
|--------|-----------------------------|
| slug | `exeq-atibaia-qa` |
| legal_name | `EXEQ Atibaia QA` |
| document | CNPJ 14 dígitos (mesmo da empresa no Focus) |
| status | `active` |
| focus_layout | `nfsen` |

| # | Critério | OK? |
|---|----------|-----|
| 1.1 | Tenant salvo e aparece na lista | ☐ |

---

## 2. Prestador (Provider)

**Master_data → Providers → Add**

| Campo | Valor sugerido |
|--------|----------------|
| tenant | o tenant do passo 1 |
| document | mesmo CNPJ do tenant/Focus |
| legal_name | razão social |
| tax_regime | `simples_nacional` |
| municipal_registration | vazio (Atibaia/nfsen costuma não exigir IM) |
| is_active | marcado |
| address | JSON com CEP real do município (se o formulário exigir/permitir) |

| # | Critério | OK? |
|---|----------|-----|
| 2.1 | Provider ativo, CNPJ alinhado ao Focus | ☐ |

---

## 3. Certificado digital

**Preferência:** API `POST /api/v1/certificates/upload` (multipart: `file`, `cnpj`, `label`, `password`) — o Admin lista/consulta; upload completo via Admin pode ser limitado (arquivo/senha).

**Accounts → Digital certificates** (após upload): conferir

| Campo | Esperado |
|--------|----------|
| tenant / provider | tenant e prestador corretos |
| cnpj | igual ao prestador |
| is_primary | `True` |
| status | `active` (ou `expiring`) |
| not_after | data futura |
| key_usage | ex.: `["das"]` se for validar gate DAS depois |

| # | Critério | OK? |
|---|----------|-----|
| 3.1 | Certificado aparece no Admin como primary/ativo | ☐ |
| 3.2 | CNPJ do cert = CNPJ do Provider | ☐ |

> Se o objetivo for só NFS-e Focus neste ciclo, 3.x é configuração da empresa; falha aqui não bloqueia necessariamente a emissão Focus.

---

## 4. Tomador e serviço

**Master_data → Customers → Add**

| Campo | Exemplo |
|--------|---------|
| tenant | mesmo |
| document_type | `cpf` |
| document | CPF válido só dígitos |
| name | `Cliente QA E2E` |
| is_active | marcado |

**Master_data → Service catalog items → Add**

| Campo | Exemplo |
|--------|---------|
| tenant | mesmo |
| service_code | `1.01` |
| description | `Serviço QA E2E` |
| codigo_tributacao_nacional_iss | código nacional ISS (ex. usado nos smokes) |
| is_active | marcado |

| # | Critério | OK? |
|---|----------|-----|
| 4.1 | Customer e Service salvos e ativos | ☐ |

---

## 5. Perfil fiscal + catálogo publicado

### 5.1 Fiscal profile

**Fiscal → Fiscal profiles → Add**

| Campo | Exemplo |
|--------|---------|
| tenant | mesmo |
| name | `SN-QA` |
| tax_regime | `simples_nacional` |
| status | ativo (conforme choices do model) |

### 5.2 Catálogo + regra

**Fiscal → Tax rule catalogs → Add**

1. Criar catálogo para o tenant.
2. No inline / **Municipal tax rules**, criar regra:

| Campo | Exemplo Atibaia |
|--------|-----------------|
| ibge_code | `3504107` |
| municipio_nome | `Atibaia` |
| uf | `SP` |
| service_code | `1.01` (igual ao serviço) |
| tax_regime | `simples_nacional` |
| fiscal_profile | `SN-QA` |
| iss_rate | `0.0200` |
| valid_from | data ≤ competência do teste |
| valid_to | vazio ou futuro |

3. Em `publish_checklist` do catálogo, marcar tudo `true`:

```json
{"csv_validated": true, "rules_reviewed": true, "terms_accepted": true}
```

4. Selecionar o catálogo → ação **Publicar catálogo (checklist completo)**.

| # | Critério | OK? |
|---|----------|-----|
| 5.1 | Perfil fiscal criado | ☐ |
| 5.2 | Regra IBGE `3504107` + `1.01` + SN | ☐ |
| 5.3 | Checklist completo | ☐ |
| 5.4 | Status do catálogo = **published** | ☐ |

---

## 6. Emissão (NfIssue)

**Issuance → Nf issues → Add**

| Campo | Valor |
|--------|--------|
| tenant | tenant do teste |
| idempotency_key | único, ex. `qa-e2e-20260719-001` |
| provider / customer / service / fiscal_profile | os cadastrados |
| ibge_code | `3504107` |
| competence_date | dentro da validade da regra |
| amount_cents | `100` (= R$ 1,00) |

Salvar → o Admin chama `create_nf_issue` (não é save cru).

| # | Critério | OK? |
|---|----------|-----|
| 6.1 | Mensagem de sucesso com `status` e `focus_ref` | ☐ |
| 6.2 | Registro aparece na lista com badge de status | ☐ |
| 6.3 | Inline **Nf issue events** com transição(ões) | ☐ |
| 6.4 | `focus_ref` preenchido (modo HTTP) | ☐ |
| 6.5 | Status final esperado: `authorized` **ou** `polling`/`submitted` (ainda processando) **ou** `rejected` com `rejection_code` legível | ☐ |

**Se ficar em polling:** selecionar a nota → ação **Consultar status no provedor (poll)** (repetir até estabilizar).

| # | Critério | OK? |
|---|----------|-----|
| 6.6 | Após poll: `authorized` ou `rejected` estável | ☐ |

---

## 7. Cancelamento (opcional, só se `authorized`)

Selecionar a nota → **Cancelar no Focus (authorized)**.

| # | Critério | OK? |
|---|----------|-----|
| 7.1 | Status → `cancelled` (pode precisar poll) | ☐ |
| 7.2 | Evento de cancelamento no inline | ☐ |

---

## 8. Reprocessamento (cenário negativo)

Emitir com dado inválido de propósito (ex. IBGE sem regra) → status `rejected`/`failed` → ação **Reprocessar** após corrigir a regra.

| # | Critério | OK? |
|---|----------|-----|
| 8.1 | Reprocessar só aceita rejected/failed | ☐ |
| 8.2 | Nova tentativa gera novo ciclo / mensagem clara | ☐ |

---

## 9. Artefatos NFS-e (PDF / XML)

Docs: v1 `NfArtifact` (xml|pdf), DER v3.1 `nf_artifacts` + `StoredFile` (`nf_pdf`/`nf_xml`).

| # | Critério | OK? |
|---|----------|-----|
| 9.1 | Após **authorized**, existem artefatos PDF e XML (lista Artefatos ou inline na emissão) | ☐ |
| 9.2 | Coluna/link **Baixar** entrega o arquivo (attachment), não só metadados | ☐ |
| 9.3 | Filtro por kind (PDF/XML) reflete linhas reais | ☐ |
| 9.4 | Ação Admin «Garantir artefatos PDF/XML» backfilla emissão autorizada sem XML/PDF | ☐ |

---

## Critérios de aceite (PO)

O E2E Admin de emissão está **aprovado** se:

1. Empresa (tenant + provider) e cadastros auxiliares (tomador, serviço, fiscal **publicado**) permitem criar NfIssue pelo Admin.
2. Certificado primary/ativo fica visível e alinhado ao CNPJ da empresa (mesmo que a NFS-e Focus use token).
3. Emissão HTTP chega a **authorized** (ou rejeição fiscal clara, sem erro 500 do Hub).
4. Poll e cancelamento (quando authorized) funcionam pelas ações do Admin.
5. PDF (DANFSe) e XML estão disponíveis para download no Admin (Artefatos / emissão).

---

## Dados de referência rápida (Atibaia)

| Item | Valor |
|------|--------|
| IBGE | `3504107` |
| Layout | `nfsen` |
| Regime | Simples Nacional |
| Admin | `/admin/` |

---

## Resultado da execução

| Campo | Preencher |
|--------|-----------|
| Data | |
| Executor | |
| Ambiente (homolog/prod Focus) | |
| Resultado | ☐ Aprovado / ☐ Reprovado |
| Observações | |
