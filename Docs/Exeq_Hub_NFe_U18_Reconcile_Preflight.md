# EXEQ Hub — U18 reconciliação RF-46 + preflight XML RF-41

| Campo | Valor |
|-------|--------|
| Base | LLR RF-46 · RF-41/EX-PRE-04 · I5 poll |
| Status | **done (código)** 2026-08-07 |

## Escopo

| Item | Entrega |
|------|---------|
| **RF-46** | Beat `nfe.reconcile_stale` · `apps/nfe/reconciliation.py` — reengata `polling` órfão; `submitting` com chave → polling; sem chave → `failed` `SUBMIT_ORPHAN` |
| **RF-41 lite** | `integrations/sefaz_nfe/xml_preflight.py` — árvore mínima + Signature **antes do POST** HTTP (`rejection_code=XSD`, sem rede) |

## Config

| Env | Default | Uso |
|-----|---------|-----|
| `NFE_RECONCILE_STALE_SECONDS` | `120` | idade mínima sem update para considerar órfã |
| `NFE_RECONCILE_INTERVAL_SECONDS` | `120` | intervalo beat |
| `NFE_RECONCILE_BATCH_LIMIT` | `50` | teto por run |

## Fora / residual

- Pacote **XSD oficial** embutido (S-02 full) — ops/download NT; preflight não substitui XSD federal
- **G-EMIT-NFE** continua ops (IE + SEFAZ homolog)
- Contingência SVC (pós G-EMIT)
- Cancel órfão: ampliado em **U19** (`cancel_requested` → restore authorized)

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_u18_reconcile.py -q
```
