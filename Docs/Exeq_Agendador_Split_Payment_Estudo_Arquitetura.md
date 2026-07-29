# EXEQ Agendador — Estudo: Split Payment e Arquitetura de Dados

| Campo | Valor |
|-------|-------|
| Documento | Estudo técnico-produto (consultoria de fábrica) |
| Status | **Análise — sem implementação** |
| Data | 2026-07-28 |
| Produto proposto | **EXEQ Agendador** (módulo de agenda no ecossistema Hub) |
| Depende de | ADR-SCHED-001 (proposta), v2 (arquitetura), v3.1 (DER), billing Hub, barbearia-saas (referência) |
| Objetivo | Orientar direção/PO antes de desenvolver split e decidir se o Agendador usa o mesmo banco |

---

## 1. Resumo executivo (1 minuto)

| Pergunta | Resposta recomendada |
|----------|----------------------|
| O que é “split” no Agendador? | Dois conceitos distintos — **não misturar no desenho**. |
| Começar por qual? | **Split operacional** (razão de comissão / quem deve a quem), igual ao barbearia-saas. |
| Split de PSP (Asaas marketplace)? | **Viável depois**, só quando houver subcontas/`walletId` e regra de negócio clara (taxa plataforma ou repasse automático). |
| Mesmo banco do Hub? | **Sim — melhor arquitetura agora.** Um Postgres, mesmo `tenant_id`, app `scheduling` no monólito modular. |
| Banco separado agora? | **Não recomendado** — custo alto, sync frágil, contradiz v2/v3.1. |
| Desenvolver já? | **Não.** Este documento é estudo; implementação exige ADR + amend DER. |

---

## 2. Nome e posicionamento de produto

**EXEQ Agendador** = domínio operacional de agenda (profissional, horário, bloqueio, agendamento, depósito, comissão, WhatsApp), **dentro do EXEQ Hub** como módulo, não como segundo SaaS com login/tenant próprios.

| Núcleo Hub (hoje) | EXEQ Agendador (proposto) |
|-------------------|---------------------------|
| NFS-e, alíquotas, RTC | Agenda e disponibilidade |
| Cobrança B2B (boleto/Pix via Inter/Asaas/C6) | Sinal / saldo do atendimento |
| DAS | Comissão e fechamento diário |
| Tenant fiscal | Mesmo tenant (um CNPJ = uma conta) |

Valor para o investidor: **um produto, um tenant, um contrato** — fiscal + operação do salão no mesmo ecossistema.

---

## 3. Dois significados de “split” (crítico)

### 3.1 Split operacional (ledger interno)

**O que é:** o sistema calcula e registra “o profissional X tem direito a R$ Y” após o serviço. O dinheiro pode continuar na conta do salão; o pagamento ao profissional é **fora do PSP** (PIX manual, folha, transferência semanal) ou via transferência posterior.

**O que o barbearia-saas já faz:**

- `commission_rules` — percentual (basis points), escopo por unidade/profissional/serviço  
- `commission_entries` — lançamento ao **completar** o agendamento (`pending` → `approved` → `paid`)  
- `appointment_financials` — preço, sinal (`deposit`), desconto, método do saldo  
- **Não** é split automático no gateway; é **contabilidade operacional**

**Adequação ao Agendador:** **alta**. Casa com o dia a dia da barbearia brasileira. Não exige KYC de cada barbeiro no Asaas. Pode ir na mesma planta do módulo de agenda.

### 3.2 Split de pagamento no PSP (marketplace / wallets)

**O que é:** na cobrança, o gateway **divide o valor líquido** entre carteiras no momento do recebimento (ex.: Asaas `splits[]` + `walletId`).

| Aspecto | Implicação |
|---------|------------|
| Pré-requisito | Cada destinatário precisa de **conta Asaas** (subconta) e `walletId` |
| Momento | Repasse **no recebimento** (não “paga sexta-feira após aprovação”) |
| Hub hoje | Porta `PaymentGateway` registra cobrança **única**; **sem** suporte a `splits` / subcontas |
| Inter / C6 | Estudos de billing do Hub **não** cobrem marketplace split; foco é cobrança do tenant |
| Quando usar | Taxa da plataforma EXEQ, franquia, ou profissional com conta própria no PSP |

**Regra Asaas (resumo):** split só via API; sobre valor **líquido**; não incluir a wallet do emissor; se o repasse for futuro/condicionado a aprovação → **não** usar split — criar cobrança normal e transferir depois.

### 3.3 Matriz de decisão (fábrica)

| Cenário de negócio | Mecanismo recomendado |
|--------------------|------------------------|
| Comissão 40% ao barbeiro, paga toda sexta | **Split operacional** (`commission_entries`) |
| Cliente paga sinal Pix; salão recebe 100% | Cobrança Hub (`Charge`) ligada ao agendamento; **sem** split PSP |
| EXEQ retém 2% de taxa de plataforma | Split PSP **ou** cobrança separada / fee — decisão comercial |
| Barbeiro PJ com conta Asaas própria, recebe na hora | Split PSP (fase avançada) |
| No-show / cancelamento com regras | Ledger operacional + estorno de `Charge`; split PSP complica estorno parcial |

**Conclusão de produto:** para o MVP do EXEQ Agendador, o termo útil é **split payment operacional** (= comissão + financeiro do atendimento). O split de marketplace fica como **fase opcional**, com ADR própria.

---

## 4. O que o Hub já tem (reuso)

| Capacidade | App / port | Uso no Agendador |
|------------|------------|------------------|
| Tenant + secrets de gateway | `accounts` | Mesmo tenant; credenciais Asaas/Inter já por tenant |
| Cobrança + webhook → `paid` | `billing` (`Charge`, `PaymentEvent`) | Sinal / saldo do cliente (B2C operacional) |
| Porta de pagamento | `integrations/payments` | Estender **depois** se houver `splits` Asaas |
| Outbox / WhatsApp | `ops` / Evolution | Confirmação e lembrete de agenda |
| Motor fiscal | `fiscal` / `issuance` | NFS-e do serviço (fluxo já existente) — **não** misturar com comissão |

**Gap atual:** não há entidade de “agendamento”, nem `commission_*`, nem ligação `Charge` ↔ atendimento. A porta de pagamento não modela destinatários múltiplos.

---

## 5. Arquitetura de banco: mesmo BD ou separado?

### 5.1 Decisão recomendada

**Usar o mesmo PostgreSQL e o mesmo monólito modular do EXEQ Hub.**

Alinhado a:

- v2: Modular Monolith, um database  
- v3.1: **“schemas lógicos por app Django; um único database”** + `tenant_id` + RLS  
- ADR-SCHED-001: app `apps/scheduling` no Hub  

### 5.2 Comparativo

| Critério | Mesmo BD (recomendado) | BD separado (Agendador isolado) |
|----------|------------------------|----------------------------------|
| Login / tenant único | Natural | Sync de tenant/usuário (custo e risco) |
| Cobrança Hub ↔ sinal do agendamento | FK / mesma transação | Saga / API / dual-write |
| NFS-e após serviço | Mesmo processo de negócio | Integração frágil |
| Operação (backup, migrate, RLS) | Um runbook | Dois |
| Isolamento de falha | Médio (módulo bem delimitado) | Alto |
| Time e time-to-market | Menor | Maior |
| Conformidade com docs oficiais | Sim | Exige nova ADR de plataforma |

### 5.3 Quando reconsiderar BD separado

Só se **todas** forem verdadeiras no futuro:

1. Escala/agenda com carga que ameace o OLTP fiscal; **e**  
2. Equipes/deploy independentes com SLA distinto; **e**  
3. Orçamento para plataforma de eventos/sync confiável.

**Hoje nenhuma dessas condições se aplica.** Separar agora seria over-engineering.

### 5.4 O que “mesmo BD” **não** significa

- Não misturar tabelas fiscais com regras de agenda no mesmo service.  
- Não colocar comissão dentro de `Charge` sem modelo claro.  
- Fronteira: app `scheduling` (agenda + financeiro operacional + comissão) **usa** `billing.Charge` por referência opcional; **não** reimplementa gateway.

```
Tenant (accounts)
    │
    ├── billing.Charge  ←── (opcional) appointment_id / deposit_charge_id
    │
    └── scheduling.*
            appointments
            appointment_financials
            commission_rules / commission_entries
```

Schemas lógicos Django = apps; **um** cluster Postgres.

---

## 6. Desenho alvo do split operacional (fase 1 — estudo)

Sem código; contrato conceitual para o amend DER futuro:

| Entidade | Função |
|----------|--------|
| `Appointment` | Ciclo de vida do horário |
| `AppointmentFinancial` | Preço, sinal pago, desconto, saldo, método |
| `CommissionRule` | % ou valor; escopos com wildcard |
| `CommissionEntry` | Direito do profissional; status pending/approved/paid |
| `Charge` (existente) | Instrumento de cobrança do sinal/saldo no PSP |

**Fluxo operacional típico:**

1. Cliente agenda → opcional: gera `Charge` (Pix/boleto) de sinal.  
2. Webhook marca `Charge.paid` → atualiza `deposit_paid_cents`.  
3. Serviço `completed` → cria `CommissionEntry` (idempotente).  
4. Gestor aprova e marca `paid` (PIX manual ao barbeiro) **ou**, em fase 2, dispara transferência/split PSP.

Isso **é** o “split payment operacional”: a divisão econômica fica auditável **antes** de existir dinheiro dividido no gateway.

---

## 7. Fase 2 — Split PSP (Asaas), se o negócio pedir

Pré-condições de produto:

1. Modelo comercial: quem recebe automaticamente (profissional, franqueadora, EXEQ).  
2. Onboarding KYC de subcontas Asaas por destinatário.  
3. ADR específica + extensão da porta `PaymentGateway` (não só Asaas — Inter/C6 podem **não** ter equivalente; feature flag por provider).  
4. Tratamento de estorno parcial e webhook de divergência de split.  
5. Split operacional **continua** existindo como razão contábil; PSP vira **execução** do repasse, não substitui o ledger.

**Não** colocar split PSP na Sprint 1 de fundação de agenda.

---

## 8. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Confundir comissão com split Asaas | Glossário §3; roadmap em fases |
| Diluir foco fiscal do Hub | Agendador = app isolado; prioridade NFS-e/RTC permanece |
| Inventar tabelas sem DER | Bloquear código até ADR-SCHED-001 + amend v3.1 |
| Provider Inter sem marketplace | Split PSP só com `payment_provider=asaas` (ou outro com API) |
| Papéis professional/attendant | Nova ata de RBAC (já sinalizado no ADR-SCHED-001) |
| Contabilidade × caixa | Entry `paid` ≠ dinheiro no banco até conciliação |

---

## 9. Recomendações para a fábrica (ordem)

| # | Ação | Tipo |
|---|------|------|
| 1 | Aprovar ADR-SCHED-001 (Agendador no Hub) | Produto / direção |
| 2 | Registrar glossário: **split operacional** ≠ **split PSP** | Produto |
| 3 | Amend DER: entidades de agenda + financeiro + comissão (ledger) | Documento |
| 4 | Sprint fundação: models/admin/testes — **sem** API Google, **sem** split Asaas | Engenharia |
| 5 | Ligar sinal a `Charge` existente | Engenharia |
| 6 | Só então estudar ADR “Split PSP / marketplace Asaas” | Opcional |

---

## 10. Texto curto para ata (opcional)

> A fábrica recomenda que o **EXEQ Agendador** compartilhe o **mesmo banco e o mesmo monólito** do EXEQ Hub, com módulo `scheduling` e tenant único. O “split” do MVP será **operacional** (regras e lançamentos de comissão + financeiro do atendimento), reutilizando a cobrança Hub para sinal/saldo. **Split automático no gateway (Asaas wallets)** fica fora do MVP e só entra com ADR própria, após onboarding de subcontas e regra comercial definida. Banco de dados separado **não** é a melhor arquitetura neste estágio.

---

## 11. Fora de escopo deste estudo

- Implementação de código ou migrations  
- Escolha final de UI / app mobile  
- Precificação comercial da taxa EXEQ  
- Substituição do núcleo NFS-e  

---

*Documento de consultoria. Próximo artefato bloqueante: aprovação ADR-SCHED-001 + amend DER; depois ADR de split PSP se o modelo de negócio exigir repasse automático.*
