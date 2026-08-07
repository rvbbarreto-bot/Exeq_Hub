# EXEQ Hub — U14 CCe (U5-CCE-01…04)

| Campo | Valor |
|-------|--------|
| Base | U5 backlog CCe · evento **110110** · paridade I6 cancel |
| Status | **done (código)** |
| G-EMIT-NFE | Ops (HTTP real quando IE + homolog) |

## Entrega

| ID | Item | Status |
|----|------|--------|
| U5-CCE-01 | Stub + `HttpNfeProvider.carta_correcao` + assinatura 110110 | done |
| U5-CCE-02 | Artefato `xml_cce` (última CCe; seq em `last_validation.cce_n_seq`) | done |
| U5-CCE-03 | `POST /nfe/invoices/{id}/cce` · `allowed_actions: cce` · download `/artifacts/cce` | done |
| U5-CCE-04 | Hub modal + lista + detalhe | done |

## Regras

- Só `authorized`; NF-e **permanece** authorized.
- `x_correcao` 15–1000; máx. **20** CCe (`cce_n_seq`).
- Falha SEFAZ/stub → 400 / `NfeValidationError`; não grava artefato.
- cStat **135/136** → aceito (não confundir com status `cancelled` do 110111).

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_cce_u14.py -q
```

## HTTP real

Depende cert A1 + `NFE_HTTP_MODE=http` + G-EMIT pré-req ops (mesma UF/série da NF-e).
