# EXEQ Hub — Onboarding multi-CNPJ / multi-tenant (NFS-e)

| Campo | Valor |
|-------|--------|
| Comando | `manage.py nfse_onboard_tenant` |
| Serviço | `apps.issuance.onboarding.onboard_nfse_tenant` |
| Status | Entregue (pós-M5) |
| Relaciona | Plano §11 · RF-01/02 · piloto M5 |

---

## 1. Objetivo

Provisionar de forma **idempotente** uma empresa (CNPJ) pronta para emitir NFS-e Nacional no Hub:

tenant → membership → prestador → serviço → perfil + regra fiscal publicada → (opcional) A1.

Sem novas tabelas.

---

## 2. Uso (ops)

```bash
python manage.py nfse_onboard_tenant \
  --slug cliente-alpha \
  --cnpj 37229907000137 \
  --legal-name "ALPHA TECNOLOGIA LTDA" \
  --user-email admin@alpha.local \
  --user-password '***' \
  --ibge 3504107 \
  --municipio-nome Atibaia \
  --uf SP \
  --service-code 170101 \
  --fiscal-profile-name SN-ALPHA \
  --pfx /caminho/cert.pfx \
  --pfx-password '***' \
  --out .storage/onboard_cliente_alpha.json
```

Reexecutar o mesmo comando **não** duplica tenant/provider/regra.

Flags úteis:

| Flag | Efeito |
|------|--------|
| `--skip-cert` | Só cadastro; A1 depois via API/Admin |
| `--im` | Inscrição municipal do prestador |
| `--dry-run` | Mostra parâmetros sem gravar |
| segundo `--ibge` no mesmo slug | Nova versão de catálogo (copia regras + delta) |

---

## 3. Pós-onboard

1. `NFSE_CONVENIO_MODE=http` (recomendado na escala) + `nfse_smoke_convenio_http` — ver `Exeq_Hub_NFSe_Ops_Convenio_HTTP.md`
2. `nfse_check_convenio --ibge … --tenant <slug> --cnpj …`  
3. Emitir no Admin/API com o `fiscal_profile` e `service` criados  

Tomador (Customer) **não** é criado pelo onboard — cadastre na emissão ou Admin.

---

## 4. Limites

- `Tenant.document` (CNPJ) é **único global** — um CNPJ = um tenant neste modelo  
- Catálogo publicado não é editável in-place (engine fiscal); onboard publica nova versão se precisar de nova regra  
- API self-serve `/tenants` continua fora (v1 backlog)
