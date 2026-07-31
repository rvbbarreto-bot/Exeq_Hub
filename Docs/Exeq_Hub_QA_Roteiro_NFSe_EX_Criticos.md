# EXEQ Hub — Roteiro QA NFS-e (EX-* críticos) — aceite M4

Checklist operacional alinhado a `Docs/Exeq_Hub_LLR_Emissor_Proprio_NFSe_Nacional.md` §5 e ao Plano §3.1 (M4).  
Cobertura automatizada: `apps/issuance/tests/test_ex_qa.py` + `apps/issuance/tests/test_security_nfse.py` + `integrations/nfse/tests/test_convenio.py`.

## Pré-requisitos

1. Tenant lab com prestador, tomador, serviço e regra fiscal Atibaia (`3504107`).
2. `NFSE_DEFAULT_PROVIDER=sefin`.
3. Certificado A1 do prestador (cenários HTTP).
4. Admin ou API autenticada.

## Casos

| ID | Cenário | Como provocar | Esperado |
|----|---------|---------------|----------|
| EX-PRE-01 | Município sem aptidão no ambiente | `NFSE_CONVENIO_DENY_IBGE=3504107` **ou** IBGE fora da semente do ambiente; emitir | Status `rejected`; código `MUNICIPIO_NAO_ADERENTE`; **sem** chamada SEFIN |
| EX-PRE-02 | Certificado ausente/expirado/revogado | `SEFIN_HTTP_MODE=http` sem A1 válido; emitir | Status `failed`; código `CERT_NOT_USABLE`; sem emissão |
| EX-NET-02 | Timeout / rede SEFIN | Simular timeout no cliente (lab) ou firewall | Status `polling` + nova consulta; **não** `authorized` |
| EX-FIS-01 | Rejeição fiscal SEFIN | DPS inválida / código de serviço rejeitado | Status `rejected`; `rejection_code` preenchido (ex. E0xxx) visível no Admin |
| EX-PDF-01 | XML ok, PDF falha | Forçar falha do gerador DANFSe após autorização | Status permanece `authorized`; flag `pdf_pending`; XML disponível; retry Admin de artefatos |
| EX-SEC-01 | Isolamento tenant | API tenant B tenta GET nota de A | HTTP 404; nota ausente na listagem |

## Happy path (regressão rápida)

1. Emitir Atibaia em **produção controlada** (`SEFIN_ENVIRONMENT=production`, `SEFIN_HTTP_MODE=http`) → `authorized` + PDF + XML.  
2. Cancelar com justificativa ≥15 caracteres → `cancelled` + PDF CANCELADA.  
3. `manage.py danfse_m1_aceite` → cobertura ≥80%.  
4. `manage.py nfse_check_convenio --ibge 3504107 --environment production` → apto.

## Notas de ambiente (estudo adesão)

- **Produção:** Atibaia (`3504107`) na semente `NFSE_NATIONAL_IBGE_CODES`.  
- **Homolog / produção restrita:** semente `NFSE_CONVENIO_HOMOLOG_IBGE_CODES` (default vazia — Atibaia **não** apta).  
- Listagem federal completa: Portal NFS-e (monitoramento de adesões + planilha de pendentes).

## Registro do teste

| Data | Executor | Ambiente | Resultado | Evidência |
|------|----------|----------|-----------|-----------|
| 2026-07-30 | QA (bateria) + PO | ambiente real / piloto | **OK — aprovado PO** | Roteiro EX-* críticos nesta versão |

## Decisões PO (2026-07-30) — reforço formal

| # | Item | Decisão PO |
|---|------|------------|
| 1 | Ops: secrets / `DEBUG=False` + re-rodar `nfse_g_sec_p0_check` | **Aprovado** |
| 2 | Parecer G-SEC-P0 + validação fiscal PDF M1 | **Aprovado** — ressalva PDF **fechada** (PO 2026-07-30) |
| 3 | QA roteiro EX-* ambiente real | **Aprovado** — seguir desenvolvimento nesta versão |
| 4 | Marco **M5** piloto produção controlada | **Aprovado** — PO Ricardo (2026-07-30); ver § Aprovação M5 |

### Ressalva PDF (item 2) — **fechada**

Polish DANFSe (autorizada + cancelada) aceito pelo PO. Regenerar no Admin: ação **Regenerar DANFSe PDF (layout atual)**.

## Atenções go-live (futuro)

Não fazem parte do aceite M4/piloto 1 prestador já aprovado. Antes de **escala / go-live amplo**, revalidar a lista em `Docs/Exeq_Hub_Plano_Desenvolvimento_Emissor_Proprio_NFSe.md` **§11.1** (GL-01…GL-05): pentest SEC-P1-09, suite `test_security_nfse` + `test_resilience` + `test_sefin_mtls` + `test_dps_contract`, time limits Celery, `nfse_g_sec_p0_check`.

## Aprovação M5 (PO)

Roteiro completo: Plano **§11.2**. Pacote: `manage.py nfse_m5_piloto_evidence --tenant agendador-qa`.

| Data | Decisão PO | Ressalva | Evidência |
|------|------------|----------|-----------|
| 2026-07-30 | **Aprovado** — PO Ricardo | Lab local pode falhar P0-01/02 (`DEBUG`); host piloto real mantém postura G-SEC-P0 já aprovada | `.storage/sefin_m5_piloto_evidence.json` |
