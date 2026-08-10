# EXEQ Hub — U13 NF-e segurança (EX-SEC + throttle)

| Campo | Valor |
|-------|--------|
| Base | LLR EX-SEC-01 · paridade SEC-P1-02 NFS-e · análise fábrica 2026-08-07 |
| Status | **done (código)** |
| Depende | U10–U12 |

## Entrega

| Item | Implementação |
|------|----------------|
| EX-SEC-01 | Tenant B → 404 em GET invoice/list/artifacts/events de A |
| SEC-P1-02 | `NfeWriteThrottle` scope `nfe_write` em create/emit/cancel/clone |
| Config | `NFE_WRITE_THROTTLE` (default `30/min`) |

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_security_nfe.py apps/nfe/tests/test_factory_u10_u12.py -q
```

## Próximas (PO)

| Item | Quando |
|------|--------|
| RF-72 mídia outbox | `Exeq_Hub_NFe_RF72_Midia_WhatsApp.md` (**done**) |
| G-EMIT-NFE | IE + homolog SEFAZ |
