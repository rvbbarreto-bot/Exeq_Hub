# ADR-FOOD-001 — EXEQ Hub Food (Comercial → Industrial)

| Campo | Valor |
|-------|-------|
| Status | **Aprovado pelo PO** |
| Data | 2026-08-09 |
| Aprovação PO | 2026-08-09 — autoriza amend DER + **início imediato Sprint 1** |
| Autores | PO EXEQ + engenharia (fábrica) |
| Tipo | Decisão de produto + amend documental (DER) |
| Relaciona | Roadmap V1 comercial → Fase 4 inteligência; **não** substitui o núcleo fiscal do Hub |
| Amend DER | `Exeq_Hub_v3.1_Database_Design_ERD.md` → **v3.1.2** (§12B FOOD) |

---

## 1. Decisão (texto para ata)

**Decidimos autorizar a inclusão do domínio EXEQ Hub Food** no monólito multi-tenant EXEQ Hub, começando pela **Sprint 1 (fundação de dados + Order Service unificado)** e com roadmap faseado: comercial/retenção → operação → indústria → inteligência.

Com esta aprovação:

1. Fica permitido criar o app `apps/food` e suas tabelas no banco.
2. O documento DER (v3.1) é atualizado (amend **v3.1.2**) para o módulo FOOD.
3. A engenharia deixa de estar bloqueada pelo acordo “não inventar tabelas fora da planta” **para o escopo §12B**.

---

## 2. Premissas travadas pelo PO (dados de fábrica ainda genéricos)

Na ausência de dossiê de fábrica preenchido, o PO **autoriza desenvolvimento com defaults explícitos**, revisáveis na primeira negociação:

| Tema | Default PO (reversível) |
|------|-------------------------|
| Dor dominante (§3.2) | **Comercial / retenção** — V1 comercial alinhado |
| Emissão fiscal Food (§3.3) | **P2** — coexistir com emissão atual; NF-e/NFC-e Food **fora** da Sprint 1 |
| Canais V1.0 | WhatsApp + balcão via **um** Order Service |
| Pix webhook | **Compromisso V1.0/V1.1** — schema de pagamento no pedido desde Sprint 1; integração gateway na sprint de pagamento |
| Régua + cupom | **V1.1** — não bloqueia Sprint 1 |
| Mesa/comanda | **Fora** até cliente com loja física com mesa |
| Capacidade fabril / PCP | **Fase 3** — schema reserva futura só como hook de status de pedido |

**Risco aceito:** se a dor real do primeiro cliente for capacidade fabril, o go-live comercial **não** resolve a dor principal — revalidar na discovery do cliente.

---

## 3. Princípios não negociáveis (desde o V1)

1. **Order Service unificado** — uma entidade `FoodOrder` (canal é atributo, não tabela/entidade paralela).
2. **Pix automatizável** — confirmação por webhook no desenho; sem “pedido WhatsApp” com conferência manual de comprovante como fluxo oficial.
3. **Régua parametrizável (V1.1)** — não hardcode de etapas por tenant.

---

## 4. Roadmap de entrega (Food)

| Etapa | Conteúdo | Status |
|-------|----------|--------|
| **Sprint 1** | Models + admin + create order + estoque simples + testes domínio | **Feito** |
| **Sprint 2** | API/Hub mínimo pedindo + listar + Pix intent + webhook pay | **Feito** |
| **V1.1** | Régua retenção parametrizável + cupom rastreado + dashboard | **Feito** |
| **Fase 2** | Compras, delivery/rotas, marketplace (iFood/aiqfome no Order unificado) | **Feito (núcleo)** |
| **Fase 3** | Indústria: BOM, OP, capacidade, estoque reservado, MRP lite | **Feito (núcleo)** |
| **Fase 4** | Inteligência: demanda, sugestões, churn/CLV/propensão, pricing dinâmico | **Feito (heurísticas)** |
| **Hub UI ops** | Hub: pedidos (status), compras, produção, inteligência | **Feito** |
| **Marketplace HTTP** | Pull stub\|http, normalize iFood/aiqfome → Order unificado, Hub + beat | **Feito** |
| **Régua Hub** | UI réguas, tick, enrollments/dispatches | **Feito** |
| **Próximo** | Credenciais OAuth oficiais iFood/aiqfome; ML avançado se dados sustentarem | Planejado |

---

## 5. Escopo e fora de escopo (Sprint 1)

**Dentro:**  
`FoodCustomer`, `FoodProduct`, `FoodOrder` + linhas, `FoodStockBalance` / `FoodStockMovement`, service `create_order` com idempotency, admin Django, testes unitários.

**Fora da Sprint 1:**  
API pública REST, UI Hub `/hub/food/`, webhook bancário real, régua/cupom, NFS-e/NF-e do food, marketplace, BOM/PCP, mesa/comanda.

---

## 6. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Diluir foco fiscal do Hub | App `food` isolado; flag `tenant.settings.food_enabled` |
| Order “unificado só no papel” | Um model + `channel`; proibir `WhatsappOrder` |
| Retenção subestimada | V1.1 com DoD próprio (idempotência WA) |
| Fiscal P0 surpresa | Discovery 3.3; se substituir emissão → sprint fiscal antes do go-live cliente |

---

## 7. Aprovação

| Papel | Nome | Decisão | Data |
|-------|------|---------|------|
| Produto / PO | PO EXEQ Hub | **Aprovado** — início imediato | 2026-08-09 |
| Engenharia / Tech lead | Fábrica | Executa Sprint 1 | 2026-08-09 |

**Efeito do “Aprovado”:** liberar Sprint 1 de `apps/food` + amend DER v3.1.2 na mesma entrega.

---

*Ata de produto. Detalhe de tabelas no amend DER §12B.*
