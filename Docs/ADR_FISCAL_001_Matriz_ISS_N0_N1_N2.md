# ADR-FISCAL-001 — Matriz ISS multi-CNPJ (N0 / N1 / N2)

| Campo | Valor |
|-------|-------|
| Status | **Aprovado + GO desenvolvimento** (PO 2026-08-11) |
| Tipo | ADR de produto + fronteira de fábrica |
| Autores | PO + Tech Lead (fábrica EXEQ Hub) |
| Código | N0 baseline documentado; **N1+N2** em implementação nesta entrega |
| Relaciona | `MunicipalTaxRule` (v3.1) · `apps/fiscal` · Hub V4 · canal WhatsApp · estudo fiscal N0/N1/N2 |

---

## 1. Decisão

**Mantemos o núcleo fiscal N0** (regra por município × código de serviço × regime × perfil, catálogo versionado, fail-closed).

**Desenvolvemos N1 (gateway de onboarding)** e **N2 (fábrica de regras linha a linha)**.

**Não desenvolvemos** N3 (alíquota única municipal para qualquer serviço) nem **N4 ampliado em produção** (fallback nacional genérico como default).

---

## 2. Definição das faixas

### N0 — Baseline (já no produto)

| Função | Status |
|--------|--------|
| Cadastro de perfil fiscal, serviços, regras ISS manuais | Existe |
| Publish de `TaxRuleCatalog` | Existe |
| Motor `resolve_tax_rule` + snapshot na emissão | Existe |
| Emissão Hub / SEFIN / canal | Existe |
| Fail closed `TAX_RULE_NOT_FOUND` | Existe |

### N1 — Gateway (controle)

| Função | Entrega |
|--------|---------|
| Checklist de go-live por tenant/prestador | `fiscal_readiness` |
| Matriz de cobertura serviço × IBGE | `coverage_matrix` |
| Gate Hub wizard (antes de `create_nf_issue`) | `assert_emit_rule_cover` |
| Gate canal WhatsApp (sem inventar alíquota) | integra readiness |
| Tela Hub “Pronto para emitir” | `/hub/fiscal/pronto/` |

### N2 — Fábrica (cadastro escalável **por item**)

| Função | Entrega |
|--------|---------|
| Templates municipais embutidos (linhas por `service_code`) | `fiscal_templates` |
| Aplicar template a perfil + subset de serviços | Hub + domain service |
| Import CSV de regras (draft → publish via bootstrap) | domain service + Hub |
| Origem da regra (`exeq_source` em `focus_field_overrides`) | auditoria enxuta sem tabela nova |

### Explicitamente fora de escopo (N3/N4)

- Uma alíquota por município expandida “às cegas” para todos os códigos sem linha no template.
- `TAX_RULE_NATIONAL_FALLBACK` como **default de produção** (permanece flag de lab; policy fiscal separada).
- Apuração DAS / substituição do contador.
- Promessa de “compliance total automática”.

---

## 3. Princípios fiscais travados

1. **1 regra = 1 (IBGE × service_code × regime × perfil × vigência)** no catálogo publicado.
2. Mesma alíquota entre itens **só** se o template/CSV trouxer **linha explícita** por item (não correlação implícita).
3. Canal e Hub **não emitem** sem cobertura (fail closed no gate N1).
4. Multi-CNPJ: readiness por **Provider** (IBGE do endereço + perfil do tenant); catálogo continua **tenant-scoped** (v3.1).
5. Origem rastreável no N2 (`template_id` / `csv` / `manual`).

---

## 4. Critérios de aceite

| ID | Critério |
|----|----------|
| AC-N1-01 | Sem regra publicada para o par serviço+IBGE → wizard/canal **bloqueiam** com mensagem clara |
| AC-N1-02 | Tela de readiness lista checks e células faltantes da matriz |
| AC-N1-03 | Tenant com cobertura completa → emit “pronto” e wizard não bloqueia por readiness |
| AC-N2-01 | Aplicar template Atibaia SN gera **linhas** por service_code selecionado |
| AC-N2-02 | Import CSV com `service_code,ibge,iss_rate,...` publica regras via bootstrap |
| AC-N2-03 | Regras criadas por template/CSV carregam `exeq_source` |
| AC-N0 | Comportamento de emissão existente com regra ok permanece |

---

## 5. Código canônico

| Módulo | Responsabilidade |
|--------|------------------|
| `apps/fiscal/readiness.py` | N1 — checklist, matriz, assert |
| `apps/fiscal/templates_factory.py` | N2 — templates + CSV |
| `apps/fiscal/bootstrap.py` | Publish idempotente (já existia; usado por N2) |
| `apps/hub_v4` | UI readiness + aplicar template/CSV |
| `apps/channel/engine.py` | Gate N1 na confirmação/emissão |

---

## 6. Histórico

| Data | Evento |
|------|--------|
| 2026-08-10 | Estudo fiscal/contábil N0–N4 (risco de generalizar alíquota) |
| 2026-08-11 | PO autoriza desenvolvimento N1+N2; N0 baseline; N3/N4 fora |
| 2026-08-11 | GO fábrica — implementação inicial nesta entrega |

---

*Não inventar tabela fora do espírito v3.1 nesta entrega: origem em JSON da regra já existente.*
