"""Pendências de produto / engenharia — EXEQ Agendador (`apps.scheduling`).

## Entregue
- Sprint 1: modelos + admin + testes
- Sprint 2: regras de booking, overlap, FSM, API, availability
- Sprint 3: WhatsApp via Outbox → Celery → Evolution
- Sprint 4: financeiro operacional + comissão (ledger)
  (`AppointmentFinancial`, `CommissionEntry`, resolução de regra, API)

## Pendente
- RBAC: papéis attendant / professional (ata futura)
- CommissionRule.branch_id: UUID solto até model Branch
- Exclude GIST no Postgres
- Split PSP (Asaas wallets) — ADR própria
- Google Calendar sync
- Lembrete agendado (Celery beat)
- Ligação opcional `Charge` Hub ↔ sinal do agendamento
- weekday: **0 = domingo … 6 = sábado**
"""
