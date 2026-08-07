# EXEQ Hub — U9 NumberSeries concorrência (DoD #4) + checklist G-EMIT ops

| Campo | Valor |
|-------|--------|
| Base | LLR D-06 · DoD domínio #4 · G-EMIT runbook U5 |
| Status | **NumberSeries: done (código)** · **G-EMIT-NFE: aberto (ops)** |

## DoD #4 — NumberSeries

| Item | Entrega |
|------|---------|
| Lock | `select_for_update` em `reserve_next_number` |
| Race create | `IntegrityError` → re-read com lock |
| Teste | `apps/nfe/tests/test_numbering_concurrency_u9.py` (threads + `transaction=True`) |

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_numbering_concurrency_u9.py -q
# preferível com Postgres (lock real):
python -m pytest apps/nfe/tests/test_numbering_concurrency_u9.py -q
```

Critério: N workers → N números **únicos e contíguos** 1..N; `next_number == N+1`.

## G-EMIT-NFE — só ops (não fechável só com código)

Checklist curto (runbook completo: `Exeq_Hub_NFe_U5_Interestadual_CCe_G_EMIT.md`):

1. Docker/Postgres + cert A1 no tenant  
2. IE-SP + credenciamento homolog SEFAZ-SP  
3. `NFE_ENABLED=true` `NFE_HTTP_MODE=http` `NFE_HTTP_DRY_RUN=false`  
4. Série cadastrada (`PUT /nfe/config/`)  
5. Spike:

```bash
python manage.py nfe_spike_sefaz --tenant <slug> --cnpj 37229907000137 --mode http --out .storage/nfe_g_emit_sp_evidence.json
```

6. Marcar gate só se `g_emit_candidate=true` + anexar JSON  
