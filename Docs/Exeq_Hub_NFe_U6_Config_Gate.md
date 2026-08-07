# EXEQ Hub — U6 NF-e (gate T0 + config série + discard/clone)

| Campo | Valor |
|-------|--------|
| Base | LLR domínio API §8 · UI T0/T6 · FSM discard/clone |
| Status | **done (código stub)** 2026-08-06 |
| Bloqueio G-EMIT | Ops — independente desta onda |

## Entregue

| Item | API / UI |
|------|----------|
| Gate honesto | `GET /nfe/gate/` — `can_create` = AND de checks Must (flag, provider, UF, IE, cert, série) |
| Config série | `GET/PUT /nfe/config/` — provider, série, tp_amb, next_number (não regride contador) |
| Stub vs HTTP | stub: série auto-seed ok; http: exige série cadastrada + IE + cert |
| Discard | `POST …/discard` — só draft sem número |
| Clone | `POST …/clone` — rejected/failed com `number_consumed` → novo draft |
| Hub | formulário série no painel T0; ações discard/clone na lista |

## Fora desta onda

- Outbox `nfe.authorized` (RF-70) — próxima
- G-EMIT SP real / CCe HTTP
- Filtros lista + timeline events

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_config_u6.py -q
```
