# EXEQ Hub — v4 API (OpenAPI)

| Campo | Valor |
|-------|--------|
| Versão | **4.1.3-draft** |
| Data | 2026-07-24 |
| Status | **Draft** — emissão + Focus + **billing** + **DAS** + **electronic-proxies** + artefatos boleto/PDF |
| Spec machine-readable | [`Docs/openapi-v4.yaml`](openapi-v4.yaml) |
| Endpoint runtime | `GET /api/v1/openapi.json` (público) |
| Hierarquia | Contrato → v1 → v2 → v3.1 → NFS-e ref → **v4** → v5 |
| Base path | `/api/v1` |
| Auth | JWT Bearer (`POST /auth/login` → `access`) salvo webhooks / openapi |

Em conflito de contrato HTTP, prevalece `openapi-v4.yaml` após promoção; schema de dados continua v3.1.

**Fonte da verdade:** `Docs/openapi-v4.yaml` (servida em runtime).

---

## 1. Superfície 4.1 (resumo)

| Área | Paths |
|------|--------|
| Meta | `GET /openapi.json` |
| Billing | `GET/POST /charges/`, `summary`, `pdf`, `cancel`, `sync` (POST), webhooks gateway, **`/billing/provider`**, presets, cancel-motivos, Inter credentials/webhook/retry |
| DAS | `GET/POST /das/guias/`, `GET /das/guias/{id}/pdf/` |
| Proxies | `GET/POST /electronic-proxies/`, `GET /certificates/`, `POST /certificates/upload` |
| Issuance / Focus | ver YAML completo |

Providers de cobrança: `asaas` \| `inter` \| `c6` (`tenant.settings.payment_provider` ou `PAYMENT_DEFAULT_PROVIDER`). HTTP: `PAYMENT_HTTP_MODE=http` + token/base URL por provider.

---

## 2. Notas de roteamento NFS-e

| IBGE / config | Provider | Layout Focus |
|---------------|----------|--------------|
| Atibaia `3504107` (nacional) | focus | `nfsen` |
| `focus_layout=nfse` e não nacional | focus | `nfse` |
| override betha | betha | SOAP legado |

---

## 3. SEFIN direto

**Fora do v4.** Manter Focus como facade.

---

## 4. Histórico

| Versão | Data | Nota |
|--------|------|------|
| 4.0.0-draft | 2026-07-19 | Emissão + Focus |
| 4.1.0-draft | 2026-07-19 | DAS + billing + proxies + `/openapi.json`; Inter/C6 HTTP |
| 4.1.1-draft | 2026-07-20 | Billing provider config por tenant (credenciais + test-connection) |
| 4.1.2-draft | 2026-07-20 | Predefinições por tenant + emissão única/parcelada/recorrente (Inter) |
| 4.1.3-draft | 2026-07-24 | Schema Charge + PDF/summary/cancel-motivos/webhook ops; sync POST-only; Hub Provedor |
