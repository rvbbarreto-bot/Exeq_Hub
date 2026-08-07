# EXEQ Hub — U10–U12 fábrica (OpenAPI · imutabilidade · UI stub MVP)

| Campo | Valor |
|-------|--------|
| Sequência | OpenAPI → imutabilidade/gates → UI stub MVP |
| Status | **código** 2026-08-06 |
| G-EMIT / canal mídia RF-72 | **próximas** (IE ops · RF-72 após base estável) |

## U10 — OpenAPI NF-e DoD #9

- Fragmento `Docs/openapi-nfe-v1.yaml` (paths `/nfe/*`, schemas Nfe*)
- Merge em `GET /api/v1/openapi.json` via `apps/ops/openapi_views.py`

## U11 — Imutabilidade / gates

- `require_content_mutable` / `is_snapshot_frozen` em `apps/nfe/services.py`
- Bloqueio de `replace_items` / `validate_invoice` em authorized|cancelled|submitting|polling…
- Rejected/failed com `number_consumed` → clone only
- Feature flag: domínio exige `NFE_ENABLED` (gate API continua respondendo `can_create=false`)

## U12 — UI stub polish

- Modal rascunho: próximo estimado série/ambiente
- Detalhe: botão copiar chave de acesso
- Lista/filtros (U8) + gate série (U6) mantidos

## Próximas (fora desta entrega)

| Item | Quando |
|------|--------|
| RF-72 mídia DANFE/XML | `Exeq_Hub_NFe_RF72_Midia_WhatsApp.md` (**done**) |
| G-EMIT-NFE | IE + homolog SEFAZ (runbook U5/U9) |

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_factory_u10_u12.py apps/ops/tests/test_openapi.py -q
```
