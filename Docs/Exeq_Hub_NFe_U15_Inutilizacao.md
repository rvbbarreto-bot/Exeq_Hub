# EXEQ Hub — U15 Inutilização de numeração NF-e

| Campo | Valor |
|-------|--------|
| Base | LLR D-14 · ADR pós-MVP Should · gate U6 (não regrida sem inutilização) |
| Status | **done (código)** · HTTP real depende G-EMIT/cert |

## Entrega

| Peça | Local |
|------|--------|
| XML InutNFe | `integrations/sefaz_nfe/inutilizacao.py` |
| Assinatura/POST | `sign_inut_nfe_xml` · `post_nfe_inutilizacao` · `HttpNfeProvider.inutilizar` |
| URLs | `resolve_inutilizacao_url` (SP + SVRS + heurística) |
| Domínio | `apps/nfe/inutilization.py` + model `NfeInutilization` |
| API | `POST /api/v1/nfe/config/inutilize` |

## Regras

- `x_just` 15–255 · faixa `n_ini`–`n_fin` (máx. 10000)
- Bloqueia se NF-e authorized/cancelled/polling na faixa
- cStat **102** = aceito (stub sempre aceita)
- Se aceito e `next_number <= n_fin` → `next_number = n_fin + 1`

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_inutilization_u15.py -q
```

## Fora

- UI Hub completa (pode ser U15-UI)
- G-EMIT HTTP homolog
