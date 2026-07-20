# EXEQ Hub — Referência de Arquitetura: Emissão NFS-e (Focus / Nacional / Betha)

| Campo | Valor |
|-------|--------|
| Versão | **1.0.0** |
| Data | 2026-07-19 |
| Status | **Referência oficial para fábrica** (não substitui v1/v2/v3.1) |
| Hierarquia | Contrato → v1 → v2 → v3.1 → **este doc (integração NFS-e)** → v4 → v5 |
| Escopo | Decisão de arquitetura + roteamento de emissão + prompt da fábrica |
| Código | **Não implementar neste documento** — apenas especificar |

Em conflito de *dados/schema*: prevalece **v3.1**.  
Em conflito de *regra funcional de domínio*: prevalece **v1**.  
Em conflito de *engines/camadas*: prevalece **v2**.  
Este documento prevalece apenas em **estratégia de integração NFS-e** (provider, layout, Atibaia/Nacional).

---

## 1. Decisão recomendada (melhor opção)

### 1.1 O que fazer

1. **Manter TaxEngine próprio** (`apps.fiscal`) — dono de alíquotas, catálogo versionado, snapshot e overrides.
2. **Manter InvoiceEngine** (`apps.issuance`) — FSM, idempotência, poll/webhook, outbox.
3. **Focus NFe como provider default** via porta `NfseProvider`, com **dois layouts**:
   - `nfse` → API municipal Focus `POST /v2/nfse`
   - `nfsen` → API NFS-e Nacional Focus `POST /v2/nfsen` (**padrão para municípios aderentes, incl. Atibaia**)
4. **Betha** permanece como provider **legado** (SOAP), só por override explícito — **não** é o caminho padrão de Atibaia em 2026.
5. **SEFIN/ADN direto (gov.br)** fica como **fase 2** (mTLS + XML DPS) — não no MVP desta entrega.
6. Introduzir **EmissionRouter** (função pura, testável) que escolhe `(provider_kind, layout)` — **não** criar um novo “Fiscal Engine” monolítico.

### 1.2 O que não fazer

- Não criar Onion/CQRS/UoW/Repository em todo CRUD.
- Não criar engine novo sem ADR (v2 §5).
- Não hardcodar layout de centenas de municípios no domínio.
- Não fazer View/Serializer montar JSON Focus.
- Não chamar HTTP Focus/Betha/SEFIN de dentro de `apps.issuance` — só via `integrations/`.
- Não tratar Betha como default de Atibaia (`3504107`) após adesão ao Emissor Nacional.

### 1.3 Por que esta opção

| Critério | Avaliação |
|----------|-----------|
| Alinhamento docs EXEQ | TaxEngine + InvoiceEngine + NfseProvider já no v1/v2 |
| Realidade 2026 Atibaia | Município aderente ao Ambiente Nacional; migração municipal→nacional |
| ROI | Focus `/v2/nfsen` evita XML/mTLS SEFIN no MVP |
| Troca de vendor | Porta `NfseProvider` + mappers isolados |
| Complexidade | Menor solução que cobre municipal + nacional + legado Betha |

---

## 2. Arquitetura-alvo

```
API (issuance)
  → InvoiceEngine.create / process
       → TaxEngine.resolve → FiscalRuleSnapshot
       → EmissionRouter(ibge, tenant.focus_layout, settings, adhesion)
            ├─ focus + nfse   → FocusNfseProvider  → POST /v2/nfse
            ├─ focus + nfsen  → FocusNfseProvider  → POST /v2/nfsen
            ├─ betha          → BethaNfseProvider  → SOAP legado
            └─ sefin (fase 2) → SefinNfseProvider  → POST /SefinNacional/nfse
       → poll e/ou webhook → authorized | rejected | failed
       → Outbox → channel / webhooks outbound
```

### Camadas de payload (obrigatório)

1. **Canonical emission model** (domínio Hub: prestador, tomador, serviço, valores, snapshot fiscal).
2. **Mapper por `(provider, layout)`** — ex.: `to_focus_nfse`, `to_focus_nfsen`, `to_betha_rps`.
3. Adapter HTTP/SOAP só traduz transport + status → `NfseEmitResult`.

---

## 3. Matriz de roteamento (EmissionRouter)

Entrada: `ibge_code`, `tenant.focus_layout`, `tenant.settings`, flags de adesão (cache/config).

| Prioridade | Condição | `provider_kind` | `layout` | API |
|------------|----------|-----------------|----------|-----|
| 1 | `tenant.settings.nfse_provider_by_ibge[ibge]` definido | valor do override | conforme override / `focus_layout` | — |
| 2 | IBGE em `NFSE_BETHA_IBGE_CODES` **e** não marcado como nacional | `betha` | `betha_soap` | Betha SOAP |
| 3 | Município aderente ao Ambiente Nacional **ou** `focus_layout=nfsen` | `focus` | `nfsen` | `POST /v2/nfsen` |
| 4 | Default | `focus` | `nfse` | `POST /v2/nfse` |

**Atibaia (`3504107`):** default de produto = **`focus` + `nfsen`**.

`tenant.focus_layout` (v3.1, default `nfsen`) é a fonte de verdade por tenant quando o município é Focus.

---

## 4. Catálogo de endpoints (referência de implementação)

### 4.1 Focus — bases

- Produção: `https://api.focusnfe.com.br`
- Homologação: `https://homologacao.focusnfe.com.br`
- Auth: HTTP Basic (`token` / senha vazia)
- Índice agente: https://doc.focusnfe.com.br/llms.txt

### 4.2 Focus — NFS-e municipal (`layout=nfse`)

| Op | Método | Path |
|----|--------|------|
| Emitir | POST | `/v2/nfse?ref={ref}` |
| Consultar | GET | `/v2/nfse/{ref}` |
| Cancelar | DELETE | `/v2/nfse/{ref}` |
| Reenviar e-mail | POST | `/v2/nfse/{ref}/email` |
| Reenviar hook | conforme doc hooks NFSe |

Payload aninhado: `prestador`, `tomador`, `servico`, `data_emissao`, `natureza_operacao`, `optante_simples_nacional`, …

### 4.3 Focus — NFS-e Nacional (`layout=nfsen`) — prioridade Atibaia

| Op | Método | Path |
|----|--------|------|
| Emitir DPS | POST | `/v2/nfsen?ref={ref}` |
| Consultar | GET | `/v2/nfsen/{ref}` |
| Cancelar | DELETE | `/v2/nfsen/{ref}` |
| Reenviar hook | conforme doc hooks NFSEN |

Payload **plano** (não aninhado): `cnpj_prestador`, `cpf_tomador`/`cnpj_tomador`, `codigo_municipio_emissora`, `codigo_municipio_prestacao`, `codigo_tributacao_nacional_iss`, `valor_servico`, `data_competencia`, `codigo_opcao_simples_nacional`, …  
Campos: https://campos.focusnfe.com.br/nfse_nacional/EmissaoDPSXml.html

### 4.4 Focus — apoio (fase próxima, mesma fábrica ou sprint seguinte)

| Área | Uso no Hub |
|------|------------|
| Empresas CRUD | Cadastrar prestador + habilitar Ambiente NFSe Nacional H/P |
| Webhooks CRUD | Preferível a só polling |
| Municípios / JSON exemplo / itens serviço | Alimentar overrides e validação pré-envio |

Lista municípios (flag Ambiente Nacional): https://focusnfe.com.br/guides/nfse/municipios-integrados/  
Atibaia `3504107` = **aderente**.

### 4.5 SEFIN / ADN gov.br — fase 2 (não MVP desta fábrica)

| Ambiente | Host SEFIN | Host ADN |
|----------|------------|----------|
| Homolog | `sefin.producaorestrita.nfse.gov.br` | `adn.producaorestrita.nfse.gov.br` |
| Produção | `sefin.nfse.gov.br` | `adn.nfse.gov.br` |

| Op | Método | Path |
|----|--------|------|
| Emitir | POST | `/SefinNacional/nfse` `{ dpsXmlGZipB64 }` |
| Consultar | GET | `/SefinNacional/nfse/{chaveAcesso}` |
| Por DPS | GET | `/SefinNacional/dps/{idDps}` |
| Eventos | POST/GET | `/SefinNacional/nfse/{chaveAcesso}/eventos` |

Auth: mTLS certificado ICP-Brasil. Portal docs: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/documentacao-atual

### 4.6 Betha — legado

SOAP Document/Literal: `RecepcionarLoteRps`, `ConsultarSituacaoLoteRps`, `ConsultarLoteRps`, `ConsultarNfsePorRps`, `ConsultarNfse`, `CancelarNfse`.  
Usar só com override explícito.

### 4.7 Atibaia — contexto de negócio

Migração municipal → Emissor Nacional: https://www.prefeituradeatibaia.com.br/notanacional/  
Cronograma 2025–2026: Simples e demais contribuintes obrigados ao emissor nacional; sistema municipal residual para consulta.

---

## 5. Responsabilidades por módulo (não misturar)

| Módulo | Responsável por | Não responsável por |
|--------|-----------------|---------------------|
| `apps.fiscal` TaxEngine | Resolver alíquota, publish, snapshot, overrides | HTTP Focus/Betha |
| `apps.issuance` InvoiceEngine | FSM, idempotência, orquestrar emit/poll | Montar JSON Focus cru na view |
| `integrations.nfse` | Porta, factory/router, adapters, mappers | Regra de alíquota do tenant |
| `apps.ops` Outbox | Notificar pós-autorização | Emitir NFS-e |
| `apps.accounts` | `TenantSecret` Focus token, certificado A1, `focus_layout` | Lógica fiscal |

---

## 6. Dados / DER (sem inventar tabelas)

Usar o que já existe em v3.1:

- `tenants.focus_layout` (`nfsen` \| `nfse`)
- `tenants.settings` (`nfse_provider_by_ibge`, flags)
- `tenant_secrets` (`provider=focus`, `key_name=api_token`)
- `municipal_tax_rules.focus_field_overrides`
- `nf_issues.internal_payload`, `focus_ref`, `focus_status_raw`
- `fiscal_rule_snapshots`

**Permitido nesta entrega (mínimo):** campo/config de layout efetivo na resolução do provider **sem** nova tabela, se couber em `settings` + `focus_layout`.  
**Proibido:** tabelas fora do v3.1 sem ADR/atualização do DER.

Mapeamento LC116 municipal ↔ `codigo_tributacao_nacional_iss`: preferir dados em `ServiceCatalogItem` / rule overrides / JSON de config — se faltar coluna no DER, **parar e reportar** (não improvisar coluna).

---

## 7. Critérios de aceite (Definition of Done)

1. `EmissionRouter` puro com testes unitários (Atibaia → focus+nfsen; override betha; default nfse).
2. Mapper `to_focus_nfsen` a partir do NfIssue + snapshot; teste de contrato com fixture.
3. `FocusNfseProvider` escolhe path `/v2/nfse` vs `/v2/nfsen` conforme layout.
4. Fluxo emissão stub: draft → … → authorized; `internal_payload` gravado.
5. Fluxo HTTP (homolog Focus) documentado em README: token + `FOCUS_HTTP_MODE=http` + empresa habilitada Nacional.
6. Betha continua na porta; testes de contrato stub; **não** default Atibaia.
7. Nenhum HTTP fora de `integrations/`.
8. Suite `pytest` verde; regras fiscais com teste na mesma entrega.
9. Código enxuto (acordo de engenharia).

Fora do DoD desta fábrica: SEFIN direto, CNC, DANFSe ADN, NF-e produto, v4 OpenAPI completo.

---

## 8. Ordem de implementação sugerida (fábrica)

1. Estender `resolve_nfse_provider_kind` → retornar `(kind, layout)` ou equivalente enxuto.  
2. Implementar `to_focus_nfsen` + testes.  
3. Ajustar Focus adapter (emit/consultar/cancelar) por layout.  
4. Wire no `process_queued_issue` (já usa provider).  
5. Corrigir defaults/docs: Atibaia = nfsen.  
6. (Opcional mesma PR) webhook Focus inbox mínimo **ou** manter poll.  
7. Não iniciar Betha HTTP/SOAP real nesta entrega salvo pedido explícito.

---

## 9. Prompt da fábrica

Copiar o bloco abaixo integralmente para a sessão da fábrica / Cursor Agent.

````markdown
# PROMPT FÁBRICA — EXEQ Hub: Emissão NFS-e (Focus nfse/nfsen + router)

## Papel
Atue como time sênior full stack Django. Código limpo, enxuto, testado. Sem Onion/CQRS/UoW. Sem inventar tabelas fora do v3.1. Em dúvida de schema: parar e reportar.

## Documentos oficiais (ler nesta ordem antes de codar)
1. `Docs/Exeq_Hub_v1_Business_Domain_Functional_Specification.md` — domínio emissão + integrations
2. `Docs/Exeq_Hub_v2_Platform_Architecture_Engineering_Guide.md` — TaxEngine, InvoiceEngine, camadas
3. `Docs/Exeq_Hub_v3.1_Database_Design_ERD.md` — models existentes
4. `Docs/Exeq_Hub_NFSe_Emission_Architecture_Reference.md` — **estratégia desta entrega (prevalece em integração NFS-e)**
5. `.cursor/rules/exeq-engineering-agreement.mdc`

## Fontes externas (consulta, não reinventar)
- Focus índice: https://doc.focusnfe.com.br/llms.txt
- Focus emitir municipal: https://doc.focusnfe.com.br/reference/emitir_nfse
- Focus emitir Nacional: https://doc.focusnfe.com.br/reference/emitir_dps_nacional
- Campos NFS-e Nacional: https://campos.focusnfe.com.br/nfse_nacional/EmissaoDPSXml.html
- Municípios Focus (Atibaia 3504107 aderente): https://focusnfe.com.br/guides/nfse/municipios-integrados/
- Atibaia migração nacional: https://www.prefeituradeatibaia.com.br/notanacional/

## Objetivo desta entrega
Implementar a **melhor opção de arquitetura** já decidida:

1. **TaxEngine próprio permanece** (não substituir por Focus).
2. **Focus = provider default** com dois layouts:
   - `nfse` → `POST/GET/DELETE /v2/nfse`
   - `nfsen` → `POST/GET/DELETE /v2/nfsen`  ← **padrão Atibaia e municípios aderentes**
3. **EmissionRouter** (função pura) decide `(provider_kind, layout)`.
4. **Betha** só por override/allowlist legado — **não** default Atibaia.
5. **SEFIN direto gov.br = FORA DE ESCOPO** nesta entrega.

## Trabalho concreto
- Estender `integrations/nfse/factory.py` (ou módulo vizinho enxuto) para resolver `layout` além de `kind`.
- Criar mapper `to_focus_nfsen` (e manter/alinhar mapper municipal) a partir de NfIssue + provider/customer/service + `resolved_params` / snapshot / `focus_field_overrides`.
- Ajustar `FocusNfseProvider` para emitir/consultar/cancelar no path correto conforme layout.
- Garantir `process_queued_issue` grava `internal_payload` do body enviado.
- Usar `tenant.focus_layout` (default `nfsen`) e `tenant.settings.nfse_provider_by_ibge` conforme matriz do doc de referência.
- Testes unitários obrigatórios:
  - router: Atibaia → focus+nfsen; override betha; default municipal nfse
  - mapper nfsen: CPF/CNPJ, município IBGE, valor, competência, códigos
  - provider stub escolhe comportamento por layout (sem HTTP real nos testes; forçar stub como já faz o conftest)
- Atualizar README só o mínimo necessário (como emitir Nacional via Focus).
- `pytest` deve passar ao final.

## Restrições
- Não criar “Fiscal Engine” novo.
- Não implementar adapter SEFIN/ADN mTLS.
- Não expandir Betha SOAP real nesta entrega (manter stub + porta).
- Não HTTP em apps de domínio.
- Não editar migrations já aplicadas em ambiente compartilhado de forma destrutiva; só migrations novas se o DER já prever o campo (senão reportar).
- Sem comentários óbvios, sem boilerplate, sem arquivos markdown extras além de README se indispensável.

## Definition of Done
Checklist da seção 7 de `Docs/Exeq_Hub_NFSe_Emission_Architecture_Reference.md` completo + pytest verde.

## Entrega
Ao final, listar: arquivos tocados, decisões tomadas, testes adicionados, e qualquer bloqueio DER/API Focus que tenha exigido reportar em vez de improvisar.
````

---

## 10. Histórico

| Versão | Data | Nota |
|--------|------|------|
| 1.0.0 | 2026-07-19 | Decisão arquitetural pós-estudo Focus/SEFIN/Betha/Atibaia; prompt fábrica incluso |
| 1.0.1 | 2026-07-19 | SEFIN direto **diferido** (Focus facade suficiente); smoke/municípios/v4 OpenAPI na esteira |

### SEFIN direto (decisão operacional)

Não implementar nesta fase. Critério de reabertura: Focus deixar de atender município aderente ou requisito explícito de mTLS próprio.
