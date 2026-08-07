# EXEQ Hub — U7 NF-e outbox (RF-70)

| Campo | Valor |
|-------|--------|
| Base | LLR RF-70 · NFS-e `enqueue_outbox` pattern |
| Status | **done (código)** 2026-08-06 |

## Eventos

| event_type | Quando | aggregate |
|------------|--------|-----------|
| `nfe.authorized` | emit stub/HTTP authorized · poll → authorized | `nfe_invoice` |
| `nfe.rejected` | emit rejected · poll → rejected | `nfe_invoice` |
| `nfe.cancelled` | cancel SEFAZ aceito | `nfe_invoice` |

Payload `schema_version=1`: ids, série/nº, chave, protocolo, cStat, totais.

**Não** enfileira em `failed` / poll_exhausted (fora RF-70 Must).

## Dispatcher

- `apps/ops/dispatcher.py` → `_notify_nfe_lifecycle`
- Ops `tenant.settings.notify_phone` → WhatsApp texto
- RF-72 mídia tomador (DANFE/XML) se sessão canal ligar — `Exeq_Hub_NFe_RF72_Midia_WhatsApp.md`

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_outbox_u7.py -q
```
