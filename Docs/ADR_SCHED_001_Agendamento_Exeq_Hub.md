# ADR-SCHED-001 — Incluir domínio de Agendamento no EXEQ Hub

| Campo | Valor |
|-------|-------|
| Status | **Aprovado pelo PO** |
| Data | 2026-07-28 |
| Aprovação PO | 2026-07-28 — autoriza amend DER + início imediato da Sprint 1 |
| Autores | Consultoria produto + engenharia (fábrica EXEQ Hub) |
| Tipo | Decisão de produto + amend documental (DER) |
| Relaciona | Migração de regras do `barbearia-saas` (referência); produto **EXEQ Agendador**; não substitui o núcleo fiscal do Hub |
| Amend DER | `Exeq_Hub_v3.1_Database_Design_ERD.md` → **v3.1.1** (seção SCHEDULING) |

---

## 1. Decisão (texto para ata)

**Decidimos autorizar a inclusão do módulo de Agendamento no EXEQ Hub**, como domínio oficial do produto (**EXEQ Agendador**), começando pela **Sprint 1 (fundação de dados)** e com **Google Agenda apenas como integração opcional futura**, nunca como sistema principal de agenda.

Com esta aprovação:

1. Fica permitido criar o app `apps/scheduling` e suas tabelas no banco.
2. O documento DER (v3.1) é atualizado (amend **v3.1.1**) para refletir o novo módulo.
3. A engenharia deixa de estar bloqueada pelo acordo “não inventar tabelas fora da planta”.

---

## 2. Contexto (por que isso importa)

- O **EXEQ Hub** hoje é a plataforma multi-empresa de **NFS-e, cobrança e DAS**.
- O **barbearia-saas** já validou em operação regras de **agenda, horários, bloqueios, comissão e WhatsApp**.
- Unificar no Hub gera **um login, um tenant e um produto** — desde que a expansão seja **oficial na documentação**, não só no código.

---

## 3. Caminho recomendado

| Etapa | O quê | Resultado de negócio |
|-------|--------|----------------------|
| **A — Feito** | ADR + amend DER + Sprint 1 (modelos) | Planta oficial |
| **B — Feito** | Regras + API (Sprint 2) | Agenda útil no Hub |
| **C — Feito** | WhatsApp via Evolution/Outbox (Sprint 3, PO 2026-07-28) | Confirmação/cancelamento/conclusão ao cliente |
| **D — Opcional** | Sync Google Calendar (OAuth por profissional) | Conforto; não crítico |
| **E — Feito** | Financeiro operacional / comissão (Sprint 4, PO 2026-07-28) | Split operacional (ledger) |
| **F — Opcional** | Split PSP Asaas / ligação Charge↔sinal | Repasse automático |

**Não recomendado:** usar Google Calendar como “banco de agenda” principal do SaaS.

---

## 4. Google Agenda — viabilidade (resumo executivo)

| Pergunta | Resposta |
|----------|----------|
| É possível? | **Sim**, como **espelho/sincronização**. |
| É viável como motor principal? | **Não** para multi-tenant SaaS (barbearias com Gmail comum). |
| Decisão | Agenda **interna** é o padrão; Google é **opcional**. |

---

## 5. Escopo e fora de escopo

**Dentro (Sprint 1):**  
estrutura de dados (profissional, serviços de agenda, horários, folgas, bloqueios, agendamento, restrições, comissão) + admin + testes. Sem API pública e sem regra de concorrência nesta fase.

**Fora desta decisão:**  
substituir NFS-e/cobrança; migrar 100% do front do barbearia-saas de uma vez; Google Calendar na Sprint 1; novos papéis `professional`/`attendant` (pendência de produto).

---

## 6. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Diluir foco fiscal do Hub | Agenda como módulo separado; núcleo NFS-e/cobrança/DAS permanece prioridade |
| Escopo explodir | Sprints curtas; Sprint 1 só fundação |
| Papéis insuficientes | Documentar TODO; não inventar RBAC sem nova ata |
| Dependência do Google | Agenda interna é fonte da verdade |

---

## 7. Aprovação

| Papel | Nome | Decisão | Data |
|-------|------|---------|------|
| Produto / PO | PO EXEQ Hub | **Aprovado** — início imediato | 2026-07-28 |
| Investidor / Direção | | ☐ Aprovo ☐ Rejeito | |
| Engenharia / Tech lead | Fábrica | Segue execução Sprint 1 | 2026-07-28 |

**Efeito do “Aprovado”:** liberar Sprint 1 de `apps/scheduling` + amend DER v3.1.1 na mesma entrega documental.

---

*Documento de ata. Detalhes técnicos de modelos no amend DER v3.1.1 e na PR da Sprint 1.*
