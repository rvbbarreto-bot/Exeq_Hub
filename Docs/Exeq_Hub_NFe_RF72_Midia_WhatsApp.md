# EXEQ Hub — RF-72 NF-e mídia WhatsApp (DANFE + XML)

| Campo | Valor |
|-------|--------|
| Base | LLR RF-72 · paridade WA-ART NFS-e · outbox U7 RF-70 |
| Status | **done (código)** |
| Depende | U7 outbox · artefatos I1/I2 · canal WhatsApp |

## Regra

| Evento | Comportamento |
|--------|----------------|
| `nfe.authorized` + sessão `ChannelSession` (`nfe_invoice` + `emitted`) | Texto + DANFE PDF + XML → telefone da sessão; falha mídia → retry outbox |
| `nfe.authorized` sem sessão | Somente texto em `tenant.settings.notify_phone` (RF-70) |
| `nfe.rejected` / `nfe.cancelled` | Texto ops apenas (sem mídia) |

Idempotência: `nfe.authorized` · `.pdf` · `.xml` com status SENT não reenviam no retry.

## Código

| Peça | Local |
|------|--------|
| FK | `ChannelSession.nfe_invoice` · `ChannelNotification.nfe_invoice` |
| Entrega | `apps/channel/services.deliver_nfe_artifacts` |
| Dispatcher | `apps/ops/dispatcher._notify_nfe_lifecycle` |
| Migration | `channel.0005_channel_nfe_invoice_rf72` |

## Testes

```bash
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_rf72_media.py apps/nfe/tests/test_outbox_u7.py -q
```

## Ligar canal (como "ligar" RF-72)

Criar/atualizar `ChannelSession` com `nfe_invoice=<id>`, `status=emitted`, `phone_e164` do tomador/solicitante. Engine WhatsApp NF-e (fluxo emit) é backlog separado; até lá Hub/ops pode ligar a sessão manualmente ou futura UI.

## Fora de escopo

- Fluxo conversacional emit NF-e no engine (ainda NFS-e)
- Mídia em rejected/cancelled
- G-EMIT SEFAZ real
