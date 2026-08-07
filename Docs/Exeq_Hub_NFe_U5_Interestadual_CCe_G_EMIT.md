# EXEQ Hub — U5 NF-e (interestadual · RTC hooks · CCe backlog) + G-EMIT SP

| Campo | Valor |
|-------|--------|
| Base | ADR-NFE-001 U5 · LLR RF-05/23/25 · D-13 onda 1b |
| Status | **código interestadual + CCe scaffold + evidência spike G-EMIT + runbook** (2026-08-06) |
| G-EMIT-NFE (ops) | **aberto** — exige SEFAZ homolog real + `g_emit_candidate=true` |

## U5 — entregue neste ciclo

| Tema | Entrega | Fora |
|------|---------|------|
| Interestadual simples | CFOP 5xxx/6xxx (RF-05); alíquota ICMS CST00 7%/12% default; auto-CFOP no draft | ST, FCP full, DIFAL UI |
| RTC hooks | `taxes.rtc` reservado `ibs`/`cbs`/`is` nulos | Cálculo norma RTC |
| CCe | Build XML evento **110110** | **U14 full** (API/UI/stub; HTTP real com ops) |

### API motor

- `apps/nfe/tax.py` · `TAX_ENGINE_VERSION=goods-0.2.0-u5`
- `suggest_cfop` / `validate_cfop_against_ufs` / `default_icms_interestadual_rate_bp`
- `replace_items` escolhe `cfop_internal` vs `cfop_interstate` do produto

### CCe backlog (U5)

| ID | Título | Status |
|----|--------|--------|
| U5-CCE-01 | Assinar + `HttpNfeProvider.carta_correcao` | **done** → `Exeq_Hub_NFe_U14_CCe.md` |
| U5-CCE-02 | Persist `xml_cce` artifact kind | **done** |
| U5-CCE-03 | API `POST …/cce` + allowed_actions | **done** |
| U5-CCE-04 | UI Hub | **done** |

Scaffold original: `integrations/sefaz_nfe/evento_cce.py` (agora full path stub+HTTP).

---

## G-EMIT-NFE — homolog SP real

**Gate:** 1 NF-e `authorized` via Hub em **SP** homolog + XML + DANFE + snapshot imutável.

### Pré-requisitos ops (bloqueiam HTTP real)

1. IE-SP do CNPJ lab `37229907000137` (ou emitente piloto)  
2. Credenciamento SEFAZ-SP ambiente homolog (tpAmb=2)  
3. Cert A1 primary do CNPJ no tenant  
4. `NFE_ENABLED=true`, `NFE_HTTP_MODE=http`, `NFE_HTTP_DRY_RUN=false`  
5. Provider com endereço UF=SP, IBGE, CRT  

### Comando (evidência)

```bash
python manage.py nfe_spike_sefaz --tenant <slug> --cnpj 37229907000137 --mode http --out .storage/nfe_g_emit_sp_evidence.json
```

Critérios no JSON de saída:

| Campo | Esperado |
|-------|----------|
| `status` | `authorized` |
| `cStat` | `100` ou `150` |
| `access_key` | 44 dígitos, cUF `35` |
| `g_emit_candidate` | `true` |
| `artifacts.xml_authorized` | `true` |
| `artifacts.danfe_pdf` | `true` |

**Dry-run / stub NÃO marcam G-EMIT.**

### Após evidência

1. Anexar `.storage/nfe_g_emit_sp_evidence.json` (sem secrets) no ticket/release  
2. Marcar **G-EMIT-NFE** no ADR / tickets U3 DoD  
3. Manter `NFE_ENABLED=false` default multi-tenant até runbook prod  

---

## Testes (código)

```bash
# com Docker Postgres :5433
python -m pytest apps/nfe/tests/test_tax_u5.py apps/nfe/tests/test_spike_i7.py -q

# lab offline
EXEQ_TEST_SQLITE=1 python -m pytest apps/nfe/tests/test_tax_u5.py apps/nfe/tests/test_spike_i7.py -q
```

| Suite | Cobertura |
|-------|-----------|
| `test_tax_u5` | CFOP 5/6, alíquota 7/12, auto-CFOP draft, CCe 110110 build |
| `test_spike_i7` | evidence `g_emit_candidate` / artefatos (stub ≠ G-EMIT) |
