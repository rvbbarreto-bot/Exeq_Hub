# EXEQ Hub — U19 hardening + freeze fábrica NF-e

| Campo | Valor |
|-------|--------|
| Base | EX-POL double finalize · EX-FIS denegada · RF-46 cancel órfão |
| Status | **done (código)** 2026-08-07 |

## Entregas

| Item | Entrega |
|------|---------|
| Outbox idempotente | 1× `nfe.authorized` / `.rejected` / `.cancelled` / `.poll_exhausted` por invoice |
| Denegada tipada | cStat 110/301/302 → `denegada` no provider; domínio `rejected` + `last_validation.denegada` |
| Cancel órfão | `cancel_requested` stale → `authorized` + `CANCEL_ORPHAN` (reenvio seguro) |
| Ops CLI | `python manage.py nfe_reconcile_stale --limit 50` |

Amplia U18 (`reconciliation.py` inclui cancel).

## Freeze de fábrica de software (código)

Com U0–U19 + I1–I8 + multi-UF, o **MVP de código greenfield NF-e** atinge o teto fechável só por engenharia:

| Pronto em código | Ainda **ops / produto** |
|------------------|-------------------------|
| FSM, tax, snapshot, artifacts | **G-EMIT-NFE** (IE + SEFAZ homolog real) |
| HTTP dry-run/stub, poll, cancel, CCe, inut | Cert A1 prod + série prod |
| Outbox, e-mail, WA mídia, metrics, PDF retry | Contingência SVC (pós G-EMIT 1 UF) |
| EX-SEC, throttle, reconciliação | XSD oficial embutido (S-02 full) |
| OpenAPI fragment + Hub stub | RF-100 catálogo NCM versionado full |

**Próxima demanda de valor real:** executar runbook G-EMIT (`nfe_spike_sefaz --mode http`) e anexar evidência — não mais ticket factory parallel.

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest \
  apps/nfe/tests/test_u18_reconcile.py \
  apps/nfe/tests/test_u19_hardening.py \
  integrations/sefaz_nfe/tests/test_http_emit_i4.py -q
```
