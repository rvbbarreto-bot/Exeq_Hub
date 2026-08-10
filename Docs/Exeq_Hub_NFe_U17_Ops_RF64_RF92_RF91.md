# EXEQ Hub — U17 ops NF-e (RF-64 · RF-92 · RF-91)

| Campo | Valor |
|-------|--------|
| Base | LLR EX-PDF / RF-64 · RF-92 alertas · RF-91 métricas |
| Status | **done (código)** 2026-08-07 |

## Escopo

| RF | Entrega |
|----|---------|
| **RF-64** | Beat `nfe.retry_pending_danfe` · `apps/nfe/pdf_retry.py` — autorizadas com `last_validation.pdf_pending` reprocessam DANFE sem reverter status |
| **RF-92** | Poll esgotado → outbox `nfe.poll_exhausted` + dispatcher WhatsApp ops (`notify_phone`) |
| **RF-91** | `GET /api/v1/nfe/metrics/?days=30` — taxa authorize, contagem por status, cStat rejeição, filas `polling` / `pdf_pending` / `poll_exhausted` |

## Config

| Env | Default | Uso |
|-----|---------|-----|
| `NFE_PDF_RETRY_INTERVAL_SECONDS` | `900` | intervalo beat Celery |
| `NFE_PDF_RETRY_BATCH_LIMIT` | `50` | teto por run |

Certificado &lt; 30d: continua no beat `accounts.scan_expiring_certificates` (já existente).

## Arquivos

- `apps/nfe/pdf_retry.py`, `tasks.py` (`retry_pending_danfe_task`)
- `apps/nfe/outbox.py` — `EVENT_POLL_EXHAUSTED`
- `apps/nfe/polling.py` — publish no esgotamento
- `apps/nfe/metrics.py` + `NfeMetricsView`
- `apps/ops/dispatcher.py` — `_notify_nfe_poll_exhausted`
- OpenAPI: `GET /nfe/metrics/` em `Docs/openapi-nfe-v1.yaml`

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_u17_ops.py -q
```

## Fora deste pacote

- G-EMIT-NFE (ops IE + SEFAZ homolog real)
- Dashboard visual Hub (métricas só API nesta U)
