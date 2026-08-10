# EXEQ Hub — U24 ops lista (PDF pendente / denegada / retry-pdf)

| Campo | Valor |
|-------|--------|
| Status | **done (código)** 2026-08-07 |
| Base | RF-64 · U8 lista · EX-PDF |

## Entregas

| Item | Entrega |
|------|---------|
| Filtros lista | `status=pdf_pending` · `status=denegada` · `flag=pdf_pending\|denegada` |
| API | `POST /nfe/invoices/{id}/retry-pdf` · action `retry_pdf` em `allowed_actions` |
| Hub | abas **PDF pendente** / **Denegadas** · botão regenerar DANFE |

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_u24_ops_list.py -q
```

## Próximo valor real

G-EMIT ops (checklist U23 + spike HTTP). Não há gap Must de lista operacional restante.
