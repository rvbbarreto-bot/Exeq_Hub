# EXEQ Hub — U4 NF-e multi-UF (G-MULTI-10)

| Campo | Valor |
|-------|--------|
| Tipo | Catálogo + matriz QA (fábrica) |
| Base | ADR-NFE-001 §7 U4 · LLR domínio D-12 |
| Status | **catálogo código + unit tests** (2026-08-06) |
| Gate | **G-MULTI-10** = happy path real por UF (ops; **não** prometido só com este catálogo) |

## Lista U4 (10 UFs)

| UF | Authority | Homolog URL (autorizacao) |
|----|-----------|---------------------------|
| SP | próprio | `homologacao.nfe.fazenda.sp.gov.br` |
| MG | próprio | `hnfe.fazenda.mg.gov.br` |
| PR | próprio | `homologacao.nfe.sefa.pr.gov.br` |
| RS | SEFAZ-RS | `nfe-homologacao.sefazrs.rs.gov.br` |
| BA | próprio | `hnfe.sefaz.ba.gov.br` |
| GO | próprio | `homolog.sefaz.go.gov.br` |
| PE | próprio | `nfehomolog.sefaz.pe.gov.br` |
| RJ | SVRS | `nfe-homologacao.svrs.rs.gov.br` |
| SC | SVRS | `nfe-homologacao.svrs.rs.gov.br` |
| ES | SVRS | `nfe-homologacao.svrs.rs.gov.br` |

Implementação: `integrations/sefaz_nfe/endpoints.py` (`NFE_MULTI_UF_10`, `resolve_endpoints`, `qa_matrix_rows`).

## Checklist QA (sem rede = unit; homolog real = ops)

| ID | Caso | Como |
|----|------|------|
| M-01 | 10 UFs resolvem HTTPS | `pytest integrations/sefaz_nfe/tests/test_endpoints_u4.py` |
| M-02 | UF fora → erro claro | unit |
| M-03 | SP pivot inalterado | unit |
| M-04 | Stub emit por UF do Provider | lab `NFE_HTTP_MODE=stub` (XML cUF) |
| M-05 | HTTP homolog por UF | spike/`mode=http` **após credenciamento UF** |
| M-06 | G-MULTI-10 | 1 authorized real por UF da lista (evidências) |

## Fora de escopo U4 código

- Contingência SVC, CCe, inutilização, ST  
- Habilitar `NFE_ENABLED` multi-tenant prod  
- Promessa comercial 27 UFs  
