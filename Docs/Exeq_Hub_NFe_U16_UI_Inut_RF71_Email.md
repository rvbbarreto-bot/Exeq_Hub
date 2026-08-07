# EXEQ Hub — U16 UI inutilização + RF-71 e-mail

| Campo | Valor |
|-------|--------|
| Base | U15 API · LLR RF-71 · CA-BTN-042 |
| Status | **done (código)** |

## U15-UI

- Hub T0/T6: campos nIni/nFin/justificativa + botão **Inutilizar faixa**
- `POST /nfe/config/inutilize` (já U15)

## RF-71 e-mail

| Item | Implementação |
|------|----------------|
| Destinatário | payload.email → `tenant.settings.nfe_notify_email` → `customer.email` (se `nfe_email_auto` ≠ false) |
| Canal | Django `EmailMessage` + anexos XML/DANFE |
| Outbox | `_notify_nfe_lifecycle` em `nfe.authorized` |
| Falha | `NfeEmailDeliveryError` → outbox FAILED; NF-e **permanece authorized** |
| Idempotência | `last_validation.email_sent` |
| Reenvio | `POST /nfe/invoices/{id}/resend-email` · action `resend_email` · force |

### Settings tenant

```json
{
  "nfe_notify_email": "ops@empresa.com",
  "nfe_email_auto": true
}
```

### Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_rf71_email.py apps/nfe/tests/test_inutilization_u15.py -q
```
