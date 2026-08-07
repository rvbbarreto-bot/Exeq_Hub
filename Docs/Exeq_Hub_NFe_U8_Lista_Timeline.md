# EXEQ Hub — U8 NF-e lista + timeline (T1 / API §8)

| Campo | Valor |
|-------|--------|
| Base | LLR UI T1 · domínio API `events` + filtros lista |
| Status | **done (código)** 2026-08-06 |

## API

| Op | Path | Notas |
|----|------|-------|
| GET | `/nfe/invoices/` | `status` (incl. `processing`), `q`, `days` (default 30; `0`=all), `date_from`/`date_to`, `all=1` |
| GET | `/nfe/invoices/{id}/events` | timeline ordenada; metadata sem body SEFAZ bruto |

Busca `q`: nº, chave, protocolo, idempotency, nome/doc destinatário.

## Hub

- Filtros período + busca na tela NF-e
- Detalhe: carrega timeline via `events`

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_listing_u8.py -q
```
