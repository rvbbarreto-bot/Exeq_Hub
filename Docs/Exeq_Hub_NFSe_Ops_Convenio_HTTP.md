# EXEQ Hub — Ops: convênio HTTP ADN (multi-município)

| Campo | Valor |
|-------|--------|
| Demanda | Ativar `NFSE_CONVENIO_MODE=http` + smoke multi-IBGE |
| Comando | `manage.py nfse_smoke_convenio_http` |
| Relaciona | RF-01 · onboarding multi-CNPJ · Plano §11 |

---

## 1. Por quê

Com `stub`, só a semente (`NFSE_NATIONAL_IBGE_CODES`, ex. Atibaia) fica apta.  
Para **municípios aderentes reais** do Portal/ADN, o host deve usar **http + mTLS** (A1 do prestador). Sem cert o ADN responde **496**.

---

## 2. Checklist ops (piloto → escala)

1. No `.env` do host:
   ```env
   NFSE_CONVENIO_MODE=http
   SEFIN_ENVIRONMENT=production   # ou homolog, alinhado ao ADN
   # ADN_PARAM_BASE_URL=          # só se override
   ```
2. Reiniciar Django/Celery para carregar o env.
3. Smoke:
   ```bash
   python manage.py nfse_smoke_convenio_http \
     --require-http-mode \
     --tenant agendador-qa \
     --cnpj 37229907000137 \
     --environment production \
     --ibge-list 3504107,3550308 \
     --out .storage/sefin_convenio_http_smoke.json
   ```
4. Conferir `aptos` no JSON; IBGE não aderente deve aparecer `apto=false` (fail-closed).
5. Emitir smoke no tenant após IBGE apto + onboarding.

Lab local pode permanecer em `stub` para testes sem ADN.

---

## 3. Evidência

Arquivo padrão: `.storage/sefin_convenio_http_smoke.json`  
Campos: `nfse_convenio_mode`, `mtls`, `results[]` com `ibge_code` / `apto` / `source`.
