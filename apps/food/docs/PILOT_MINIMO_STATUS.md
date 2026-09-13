# Food — Escopo piloto mínimo (PO)



**Autorização PO:** 2026-08-21  

**Referência:** ADR-FOOD-001, `FOOD_PAYMENTS_DELIVERY_QA.md`, `QA_FASE_A_STUB_ROTEIRO.md`



---



## Arquitetura Hub (piloto unificado)



Operação diária concentrada no **Hub Food** — sem depender do Admin Django para cadastros básicos:



| Área | Hub | Admin (avançado) | API |

|------|-----|------------------|-----|

| Produtos | `/hub/food/produtos/` | BOM, estoque | `food/products` |

| Clientes | `/hub/food/clientes/` | vínculo fiscal | `food/customers` |

| Pedidos | `/hub/food/pedidos/` | — | `food/orders` |

| Pagamento | detalhe do pedido | `FoodPayment` | webhook MP |

| Produção | `/hub/food/producao/` | fichas técnicas | — |



**Fora do piloto:** links **ocultos** na navegação. URL legada → **404** com página explicativa (sem redirect surpresa).



---



## Escopo ativo



Pedidos (multi-item), produtos, clientes, produção, pagamento Pix/cartão, webhook, histórico de pagamentos, WhatsApp API.



---



## Gaps pendentes



| Prioridade | Item |

|------------|------|

| P1 | QA Fase A stub — roteiro completo antes go-live |

| P2 | Edição de produto/cliente no Hub (hoje só criação + listagem) |

| P2 | Admin avançado (BOM) — link contextual a partir do Hub produção |

| P3 | Filtros avançados na lista de pedidos |



---



## Onde alterar escopo



`apps/food/pilot_scope.py` — `PILOT_HUB_SECTIONS`, `PILOT_ADMIN_MODELS`


