# Status Report QA — EXEQ Agendador

| Campo | Valor |
|-------|-------|
| Data/hora | 2026-07-28 (noite) / execução ~2026-07-29 02:00 UTC |
| Papel | Time QA sênior (fábrica) |
| Escopo | Seed + testes de integração (pytest) + exploratório API |
| Ambiente | Local — Django `http://127.0.0.1:8000`, Postgres do compose |
| Autorização PO | Seed + integração + exploratório (obrigatórios / bugs) |

---

## Veredito

**Integração automatizada: APROVADA** (28/28 pytest `apps/scheduling`).  
**Exploratório API: APROVADO COM RESSALVAS** (20 PASS, 0 FAIL, **1 BUG** de validação/UX).  
**UI/layout:** **N/A nesta rodada** — módulo Agendador ainda sem telas Hub dedicadas; exploratório foi **API-only**.

---

## 1. Seed executado

```text
python manage.py seed_scheduling_qa --reset-hours
```

| Item | Valor |
|------|--------|
| Comando | `apps/scheduling/management/commands/seed_scheduling_qa.py` |
| Resultado | **OK** |
| Tenant | `agendador-qa` |
| Usuário | `agenda.qa@exeq.local` / `AgendaQa123!` |
| Massa | 1 provider, 2 customers, 1 professional, 2 services, vínculo N:N, horários seg–sex 09–18, regra comissão 40% |

IDs fixos documentados na saída do comando (reproduzíveis para roteiros).

---

## 2. Testes de integração (pytest)

```text
python -m pytest apps/scheduling/ -q
```

| Métrica | Resultado |
|---------|-----------|
| Coletados | 28 |
| Passou | **28** |
| Falhou | 0 |
| JUnit | `Docs/qa_scheduling_pytest_junit.xml` |

Cobertura exercitada: models, booking rules, services (overlap/FSM/idempotency), API, WhatsApp/outbox, finance/comissão, resolução de regra.

**Aviso ambiente:** teardown ocasional `test_exeq_hub is being accessed by other users` (sessão paralela) — não afetou resultado dos asserts.

---

## 3. Exploratório API

```text
python scripts/qa_scheduling_exploratory.py --base-url http://127.0.0.1:8000
```

Log resumido: `Docs/QA_SCHEDULING_EXPLORATORY_LAST_RUN.md`

### Cenários PASS (amostra)

- Login JWT tenant QA  
- Listagens: professionals, services, business-hours, appointments, commission-rules  
- Validação obrigatórios: appointment vazio → 400 com `customer_id`, `professional_id`, `service_id`, `starts_at`, `idempotency_key`  
- Professional sem `name` → 400  
- Availability com slots  
- Rejeição de horário no passado  
- Create + idempotency + overlap + FSM confirm→check-in→start→complete  
- Financial após complete + commission entries  

### BUG encontrado

| ID | Severidade | Achado | Evidência |
|----|------------|--------|-----------|
| QA-SCHED-001 | **Média (UX/API)** | `POST /scheduling/services/` com `duration_minutes=1` retorna **HTTP 500** (CheckConstraint no banco) em vez de **400** validado no serializer | Exploratório |

**Impacto:** cliente API vê erro interno; campos fora da faixa 5–480 não são validados na camada HTTP.  
**Sugestão fábrica:** `validate_duration_minutes` no serializer (ou `MinValueValidator`/`MaxValueValidator` no model + tratamento DRF).

### Notas (não bloqueantes)

| Nota | Detalhe |
|------|---------|
| Trailing slash | `GET …/professionals` sem `/` → **301** (comportamento Django/DRF padrão) |
| Layout/UI | Sem frontend Agendador no Hub nesta fase — **quebra de layout não aplicável** |

---

## 4. Campos obrigatórios (mapa exploratório)

| Recurso | Obrigatórios observados na API |
|---------|--------------------------------|
| Appointment create | `customer_id`, `professional_id`, `service_id`, `starts_at`, `idempotency_key` (≥8) |
| Professional create | `provider`, `name` (+ tenant via auth) |
| Service create | `name`, `duration_minutes`, `price_cents` (duration fora da faixa → BUG 500) |

---

## 5. Riscos / gaps de QA

1. Sem teste E2E de **UI** (cadastros/agenda visual).  
2. Sem carga/concorrência real (dois clients no mesmo slot).  
3. WhatsApp no exploratório não assertou `ChannelNotification` (coberto no pytest).  
4. Seed não limpa appointments antigos — roteiro já usa slot livre da availability.

---

## 6. Recomendações ao PO

| Prioridade | Ação |
|------------|------|
| P1 | Corrigir QA-SCHED-001 (validar duration no serializer → 400) |
| P2 | Quando houver UI Agendador, nova rodada QA layout/campos |
| P3 | Manter `seed_scheduling_qa` + `qa_scheduling_exploratory.py` no checklist de regressão |

---

## 7. Como reproduzir

```powershell
python manage.py seed_scheduling_qa --reset-hours
python -m pytest apps/scheduling/ -q
python scripts/qa_scheduling_exploratory.py --base-url http://127.0.0.1:8000
```

**Status final da execução:** integração **verde**; exploratório **verde com 1 bug médio** (validação de duração de serviço).
