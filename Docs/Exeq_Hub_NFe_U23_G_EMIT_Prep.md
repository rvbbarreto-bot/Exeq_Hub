# EXEQ Hub — U23 G-EMIT prep (OpenAPI · attempts CCe/inut · checklist)

| Campo | Valor |
|-------|--------|
| Status | **done (código)** 2026-08-07 |
| Base | U20 RF-44 · U5/U9 runbook G-EMIT |

## Entregas

| Item | Entrega |
|------|---------|
| RF-44 complete | Attempts em **CCe** e **inutilização** (`stage=cce|inut`) |
| OpenAPI | `GET /nfe/invoices/{id}/attempts` · `flags` no schema NfeInvoice |
| Checklist ops | `python manage.py nfe_g_emit_checklist --tenant <slug> --cnpj …` · `apps/nfe/g_emit_checklist.py` |
| Spike | `schema_version` + `correlation_id` validados em teste I7 |

## Uso ops (sem SEFAZ POST ainda)

```bash
# 1. Checklist local
python manage.py nfe_g_emit_checklist --tenant <slug> --cnpj 37229907000137

# 2. Quando ready_for_http_dry_run=true
python manage.py nfe_spike_sefaz --tenant <slug> --cnpj 37229907000137 --mode http --dry-run

# 3. HTTP real → evidência G-EMIT
python manage.py nfe_spike_sefaz --tenant <slug> --cnpj 37229907000137 --mode http \
  --out .storage/nfe_g_emit_sp_evidence.json
```

`ready_for_http_emit=true` **não** marca G-EMIT — só pré-req. G-EMIT = spike com `g_emit_candidate=true`.

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_u23_g_emit_prep.py apps/nfe/tests/test_spike_i7.py -q
```
