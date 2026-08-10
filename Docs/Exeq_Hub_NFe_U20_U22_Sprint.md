# EXEQ Hub — U20–U22 sprint acelerado (factory pré-G-EMIT)

| Campo | Valor |
|-------|--------|
| Status | **done (código)** 2026-08-07 |
| Escopo | RF-44 attempts · RF-90 logs · Gate RF-01 · RF-41++ · RF-100 lite · Hub ops |

## U20 — Observabilidade

| Item | Entrega |
|------|---------|
| **RF-44** | Model `NfeTransmissionAttempt` + gravação em emit/poll/cancel · `GET …/attempts` · Admin |
| **RF-90** | `correlation_id` no attempt + log poll |

## U21 — Gate + evidence + preflight

| Item | Entrega |
|------|---------|
| Gate | IBGE, CRT, UF matriz, cert usable/expiring, CNPJ cert=emitente (http) |
| Spike | `schema_version=1.0`, correlation, tp_amb, uf, ie_present, key_cuf |
| Preflight++ | det≥1, ICMSTot, emit CNPJ · `NFE_XSD_PATH` opcional |

## U22 — Hub + catálogo

| Item | Entrega |
|------|---------|
| Hub | Badges Denegada / PDF pendente · KPIs `/nfe/metrics/` · attempts no detalhe |
| RF-100 lite | `apps/nfe/catalog.py` NCM/CFOP MVP · `catalog_version` no snapshot/validate |

## Migration

```bash
python manage.py migrate nfe
```

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_u20_u22_sprint.py -q
```

## Ainda ops

**G-EMIT-NFE** = IE + cert + `nfe_spike_sefaz --mode http` → `g_emit_candidate=true`.
