# EXEQ Hub v2 — Platform Architecture & Engineering Guide

| Campo | Valor |
|-------|-------|
| Documento | Exeq_Hub_v2 |
| Versão | **2.1.0** |
| Status | **Guia oficial de arquitetura e engenharia** |
| Data | 2026-07-19 |
| Depende de | Contrato, v1 (domínio), v3.1 (DER) |

---

## 1. Objetivo

Consolidar decisões de plataforma para implementar o EXEQ Hub como **Modular Monolith** Django idiomático, sem over-engineering.

---

## 2. Princípios

- Django First, DRF, PostgreSQL 16, Celery + Redis
- Modular Monolith + Domain Driven Modules
- Simplicidade e baixa complexidade
- **Não** usar Onion Architecture
- **Não** usar Clean Architecture além do padrão natural Django
- **Não** usar CQRS nem UnitOfWork
- **Não** criar abstrações sem benefício claro

---

## 3. Acordo de engenharia (obrigatório até o fim do projeto)

### Time

Atuar como time sênior full stack. Toda mudança material consulta a hierarquia: Contrato → v1 → v2 → v3.1 → v4 → v5.

### Código limpo e enxuto

1. Entregar a menor solução correta.
2. Evitar boilerplate e “frameworks internos”.
3. Sem comentários que repetem o código.
4. Um módulo / função / classe = uma responsabilidade clara.
5. Reutilizar Django (auth hasher, migrations, admin pontual, ORM) em vez de reinventar.

### Testes

1. Regra de domínio ou constraint de model → **teste unitário na mesma entrega**.
2. Priorizar testes de model, domain service e application service.
3. Regras fiscais/monetárias exigem revisão humana além do verde do CI.

### Camada oficial

```
View → Serializer → Application Service → Domain Service → Django ORM
```

Integrations externas apenas via ports em `integrations/` + Outbox para side-effects.

---

## 4. Estrutura de repositório (alvo)

```
exeq_hub/
  manage.py
  pyproject.toml
  config/                 # settings, urls, celery
  apps/
    accounts/
    master_data/
    fiscal/
    issuance/
    billing/
    das/
    channel/
  integrations/           # ports + adapters
  shared/                 # tenancy, money helpers, exceptions
  platform/               # audit, outbox, storage, health
  tests/                  # ou testes colocalizados por app
  Docs/                   # especificação oficial
```

Sprint 0 cria o esqueleto mínimo (`config`, `apps.accounts`, `shared`) sem apps futuros vazios em excesso.

---

## 5. Domain Engines oficiais

| Engine | Responsabilidade | App / tabelas |
|--------|------------------|---------------|
| TenantEngine | tenant, membership, RBAC, features | accounts |
| TaxEngine | resolução de alíquota, publish de catálogo | fiscal |
| InvoiceEngine | FSM NFS-e, idempotência emissão | issuance |
| BillingEngine | cobrança + pagamento | billing |
| CertificateEngine | A1, rotação, uso | accounts + stored_files |
| WebhookEngine | inbox inbound + outbox outbound | billing + platform |

**Não** criar novos engines sem ADR.

---

## 6. Storage

```
Storage Interface → Local | S3 | MinIO
```

Metadados em `stored_files` (v3.1). Nenhum path solto em tabelas de domínio.

---

## 7. Outbox

```
Mudança de domínio commitada → OutboxMessage → Worker → WhatsApp | Email | Webhook
```

Nenhuma integração externa síncrona dentro da emissão de nota.

---

## 8. Tenancy & segurança (plataforma)

- Login: `tenant_slug` + email + senha (ADR-DB-003 / v3.1)
- RBAC: `TenantMembership` + `TenantRole` (não Group global como fonte de verdade)
- RLS PostgreSQL + `TenantModel` na aplicação
- `bypass_rls` só em código de infraestrutura, com teste negativo
- Secrets versionados (`tenant_secrets`); certificados via `CertificateEngine`

---

## 9. ADRs de plataforma (resumo)

| ID | Decisão |
|----|---------|
| ADR-P-001 | Modular Monolith Django; sem microserviços no MVP |
| ADR-P-002 | Camadas View→…→ORM; engines oficiais apenas |
| ADR-P-003 | Celery + Redis para async; Kafka fora do MVP |
| ADR-P-004 | Testes unitários obrigatórios por entrega de regra |
| ADR-P-005 | Código enxuto: rejeitar PRs verbosos sem ganho funcional |
| ADR-DB-* | Ver Exeq_Hub_v3.1 (nomenclatura, money, outbox, RLS) |

---

## 10. Observabilidade & CI (baseline Sprint 0+)

- `correlation_id` em requests de negócio
- Health endpoint simples
- Lint/format: Ruff (+ Black se necessário)
- Pytest no CI antes de merge
- Sentry/OTel: Sprint seguinte à fundação estável — não bloquear Sprint 0

---

## 11. Ordem de sprints (dados + apps)

Alinhado ao v3.1 §22 e à ordem de dependência do v1:

0. Fundação Django + `accounts` (+ testes)
1. Fechar accounts (auth JWT mínimo)
2. `master_data`
3. `fiscal`
4. `integrations` ports + `issuance`
5. `billing`
6. `das`
7. `channel` (opcional)

---

## 12. Conflitos

Se v1 (regra) divergir de v3.1 (schema): **schema v3.1** + ajustar texto do v1 em PR de docs.  
Se código divergir destes docs: **corrigir o código**, não silenciar o doc.

---

## Histórico

| Versão | Mudança |
|--------|---------|
| 2.0 | Stub de princípios |
| **2.1.0** | Guia expandido + acordo de engenharia + estrutura + ADRs + sprints |
