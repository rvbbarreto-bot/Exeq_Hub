# EXEQ Hub — DoD de Segurança: Emissor NFS-e Nacional (SEFIN/ADN)

| Campo | Valor |
|-------|--------|
| Tipo | Definition of Done — segurança (anexo de board) |
| Epics | **NFSE-A-EMIT** · **NFSE-OPS** (não Trilha B DANFSe) |
| Status | **Parecer G-SEC-P0: aprovado PO (2026-07-30)** — ressalva PDF M1 **fechada**; QA EX-* aprovado |
| Data | 2026-07-30 |
| Relaciona | `ADR_NFSE_001_Emissor_Proprio_Nacional.md` · `Exeq_Hub_LLR_Emissor_Proprio_NFSe_Nacional.md` (RF-61, EX-PRE-02, EX-SEC-*) · `Exeq_Hub_Plano_Desenvolvimento_Emissor_Proprio_NFSe.md` · `Exeq_Hub_Inter_Security_Hardening.md` (padrão de checklist) |
| Fora deste DoD | Layout DANFSe (NFSE-B); Vault/HSM obrigatório no piloto; pentest completo pré-M5 |

---

## 1. Objetivo

Definir **critérios mensuráveis de segurança** para o caminho SEFIN/ADN do Hub, anexáveis às stories dos epics **NFSE-A** (emissão) e **NFSE-OPS** (operação/produção), sem misturar com polish de PDF.

**Princípio:** piloto M5 com 1 prestador exige **postura mínima fail-closed**; go-live amplo exige **DoD completo + evidência de teste**.

---

## 2. Modelo de ameaça (resumo)

| Superfície | Risco | Controle esperado |
|------------|-------|-------------------|
| Certificado A1 (PFX + senha) | Roubo de chave → emissão fraudulenta | Criptografia em repouso; senha em `TenantSecret`; sem A1 no git / `.env` versionado |
| mTLS SEFIN/ADN | MITM / handshake frágil | Verify de servidor ligado; cliente isolado em `integrations/nfse`; sem `verify=False` |
| XMLDSig / parse XML | XXE, Signature Wrapping, DoS por entidade | Parser endurecido; assinar/processar o nó correto |
| API emissão/cancel/consulta | Abuse, double-submit, esgotar cota gov | Idempotência; throttle; autenticação tenant |
| Artefato XML/PDF | IDOR multi-tenant (EX-SEC-01) | RLS + filtro app + download autenticado |
| Logs / Admin | Vazamento PFX, senha, stack | RF-61; `DEBUG=False`; Admin com controle de acesso |
| Dependências / repo | CVE, segredo commitado | SCA + SAST + secret scan no CI (antes de escala) |

---

## 3. Escopo por epic

| Epic | O que entra neste DoD |
|------|------------------------|
| **NFSE-A-EMIT** | Cert no fluxo HTTP; mTLS; XMLDSig/XXE; timeout/retry; idempotência; rejeição/cert gates (EX-PRE-02); isolamento Focus×SEFIN |
| **NFSE-OPS** | Secrets de produção; beat alerta cert; runbook SEFIN; rate limit; RLS/artefato; Admin; CI scanners; pentest; segregação homolog×prod |
| **NFSE-B-DANFSE** | **Fora** — salvo “PDF/XML sem dados sensíveis em log INFO” (já coberto por RF-61) |
| **NFSE-QA** | Executar checklists deste DoD + `Exeq_Hub_QA_Roteiro_NFSe_EX_Criticos.md` |

---

## 4. Gates de aceite

### G-SEC-P0 — Antes do piloto M5 (produção controlada, 1 prestador)

Obrigatório para declarar piloto seguro. **Não** exige Vault/HSM.

| ID | Critério | Evidência |
|----|----------|-----------|
| SEC-P0-01 | `DEBUG=False` no ambiente do piloto | Config / boot log |
| SEC-P0-02 | `DJANGO_SECRET_KEY` e `FIELD_ENCRYPTION_KEY` próprios (não defaults de lab) | Checklist ops |
| SEC-P0-03 | A1 do prestador **não** está no git; PFX cifrado + senha em `TenantSecret` | Revisão + Admin |
| SEC-P0-04 | Certificado de **produção** distinto do de lab/homolog | Inventário cert |
| SEC-P0-05 | Cliente SEFIN com verificação TLS ativa (sem desligar CA) | Code review / teste |
| SEC-P0-06 | Beat `accounts.scan_expiring_certificates` **ativo** no ambiente | Celery beat running |
| SEC-P0-07 | Emissão com `idempotency_key` não duplica nota no retry | Teste automatizado já existente + smoke |
| SEC-P0-08 | Tenant A não acessa `NfIssue`/artefato de tenant B (API) | Teste EX-SEC-01 ou roteiro QA |
| SEC-P0-09 | Logs SEFIN sem senha/PFX/XML completo em INFO (RF-61) | Amostra de log sanitizada |
| SEC-P0-10 | Runbook SEFIN indisponível conhecido da ops (§12.1 do Plano) | Doc + briefing |

**Saída:** PO/Tech Lead assinam “piloto autorizado sob G-SEC-P0”.

---

### G-SEC-P1 — Antes de go-live amplo (mais de 1 tenant / volume)

| ID | Critério | Evidência |
|----|----------|-----------|
| SEC-P1-01 | `ALLOWED_HOSTS` explícito do domínio de produção | Config |
| SEC-P1-02 | Throttle (ou equivalente) em emissão/cancelamento NFS-e | Config + teste abuse |
| SEC-P1-03 | Parse XML do caminho DPS/evento **sem** resolução de entidades externas (XXE) | Teste unitário + review |
| SEC-P1-04 | RLS (ou equivalência comprovada) em tabelas de artefato NFS-e | Migration/policy + teste IDOR Admin/API |
| SEC-P1-05 | Admin: acesso restrito (staff mínimo; preferível 2FA e/ou IP allowlist) | Ops checklist |
| SEC-P1-06 | CI: `bandit` (ou SAST equivalente) + `pip-audit`/`safety` + secret scan (`gitleaks` ou equivalente) | Pipeline verde |
| SEC-P1-07 | Timeout SEFIN com política de recuperação documentada; retry com teto (sem martelar 4xx) | Teste EX-NET-* + doc |
| SEC-P1-08 | CORS restritivo se houver front separado (nunca `*` + credentials) | Config (N/A se só Admin same-origin) |
| SEC-P1-09 | Pentest externo com escopo §6 executado e achados P0/P1 tratados ou aceitos por PO | Relatório |

**Saída:** parecer go-live de segurança (PO + Tech Lead).

---

### G-SEC-P2 — Contínuo / pós-piloto (backlog NFSE-OPS)

Não bloqueia M5; agenda após estabilidade.

| ID | Item | Status |
|----|------|--------|
| SEC-P2-01 | Cofre externo (Vault / cloud Secrets Manager) para raiz criptográfica e/ou material A1 | backlog |
| SEC-P2-02 | Avaliar HSM/KMS se volume ou requisito contratual de cliente | backlog |
| SEC-P2-03 | Validação XSD oficial DPS/NFS-e no CI (contrato) | **parcial** — `assert_dps_structure` no build DPS; XSD oficial embutido fica pendente |
| SEC-P2-04 | Carga/resiliência: latência/5xx SEFIN não esgota workers | **feito (MVP)** — time limits Celery + budget HTTP; ver Plano §12.1 |
| SEC-P2-05 | Revisão quinzenal NT + CVEs em `lxml`/`cryptography`/`signxml` | backlog (CI `pip-audit` já em P1) |
| SEC-P2-06 | Eliminar ou reduzir janela de chave privada em arquivo temporário no handshake mTLS | **feito** — PEM só durante `load_cert_chain`; `TemporaryDirectory.cleanup()` imediato |

---

## 5. Checklist de board (copiar para story)

### Story tipo: `NFSE-OPS — G-SEC-P0 piloto`

- [x] SEC-P0-01…P0-10 — **parecer PO aprovado** (ops executa secrets/`DEBUG=False` no host piloto; check `nfse_g_sec_p0_check`)
- [x] Ressalva PDF M1 fechada (PO 2026-07-30) — polish DANFSe aceito; ver roteiro QA

### Story tipo: `NFSE-A — hardening emissão`

- [x] SEC-P1-03 XXE (`integrations/nfse/xml_safe.py`)
- [x] SEC-P1-07 timeout/retry teto (`SEFIN_HTTP_MAX_ATTEMPTS`; sem retry em 4xx)
- [x] EX-PRE-02 cert bloqueia sem HTTP (já coberto por teste; manter verde)

### Story tipo: `NFSE-OPS — G-SEC-P1 go-live`

- [x] SEC-P1-02 throttle `nf_issue_write`
- [x] SEC-P1-04 RLS `issuance_nfartifact` (+ download Admin por membership) — **PO autorizou; `migrate ops 0007` OK (lab Postgres 2026-07-30)**
- [x] SEC-P1-06 CI `.github/workflows/security.yml` (bandit + pip-audit)
- [x] SEC-P1-01 ALLOWED_HOSTS via `DJANGO_ALLOWED_HOSTS` (ops: domínio real no piloto)
- [x] SEC-P1-05 Admin IP allowlist (`ADMIN_ALLOWED_IPS` + middleware; 2FA ainda ops/P2)
- [x] SEC-P1-06 CI + gitleaks no workflow security
- [x] SEC-P1-08 CORS N/A (sem django-cors-headers; same-origin)
- [ ] SEC-P1-09 Pentest — **escopo preparado** (`Docs/Exeq_Hub_NFSe_Pentest_Briefing_SEC_P1_09.md`); execução/relatório pendentes → **atenção go-live amplo** (Plano §11.1 GL-01)

**Atenções go-live (futuro):** Plano `Exeq_Hub_Plano_Desenvolvimento_Emissor_Proprio_NFSe.md` §11.1 (GL-01…GL-05) — pentest + regressão `test_security_nfse` / `test_resilience` / `test_sefin_mtls` / `test_dps_contract` + pré-voo `nfse_g_sec_p0_check`.

**Ferramenta:** `manage.py nfse_g_sec_p0_check` → `.storage/sefin_g_sec_p0_check.json`
---

## 6. Escopo mínimo de pentest (aceitação)

Contratar ou executar com escopo explícito (não só “OWASP genérico”).

**Briefing operacional:** `Docs/Exeq_Hub_NFSe_Pentest_Briefing_SEC_P1_09.md` (alvos, out-of-scope, regras de engajamento, pré-voo).

Checklist resumido:

1. **Web/API OWASP** — authn/authz, IDOR tenant (nota e download de artefato).  
2. **API fiscal** — fuzz emissão/consulta/cancel; abuse sem rate limit.  
3. **TLS/mTLS** — rejeição de servidor inválido; não vazamento de chave em erro.  
4. **XML** — XXE, Signature Wrapping, entity expansion (**pedir explicitamente**).  
5. **Segredos / acesso humano** — quem exporta A1; trilha de auditoria.  
6. **Infra** (se aplicável) — exposição de portas, segregação do host que guarda PFX.

Achados **P0** bloqueiam G-SEC-P1. Achados **P1** exigem plano datado ou aceite formal do PO.

---

## 7. O que NÃO é obrigatório no piloto M5

- HSM / KMS dedicado  
- Vault corporativo (Fernet + `TenantSecret` + fail-closed bastam no P0, com risco residual aceito)  
- Pixel-perfect DANFSe / checklist 95% (Trilha B)  
- Cobertura de todos os EX-* do LLR além dos críticos já no roteiro QA  

---

## 8. RACI

| Atividade | PO | Tech Lead | NFSE-A | NFSE-OPS | QA |
|-----------|----|-----------|--------|----------|-----|
| Aprovar este DoD | A | R | C | C | I |
| Executar G-SEC-P0 | A | A | C | R | C |
| Hardening XXE / mTLS | I | A | R | C | C |
| CI scanners / prod config | I | A | I | R | C |
| Pentest + tratamento | A | R | C | C | C |

R = executa · A = aprova · C = consulta · I = informado.

---

## 9. Mensagem executiva

Segurança do emissor próprio SEFIN no Hub já tem **base sólida** (A1 cifrado, mTLS isolado, idempotência, alerta de cert, RF-61). Este DoD separa o que é **obrigatório no piloto (P0)**, o que é **obrigatório antes de escala (P1)** e o que é **evolução (P2)**, para o board não misturar HSM com DANFSe nem bloquear M5 por itens pós-piloto.

---

## 10. Histórico

| Versão | Data | Nota |
|--------|------|------|
| 0.6 | 2026-07-30 | Atenções go-live §5 + Plano §11.1 (GL-01…05) |
| 0.5 | 2026-07-30 | SEC-P1-09 briefing pentest; SEC-P2-04 time limits Celery emissão |
| 0.4 | 2026-07-30 | Ressalva PDF fechada; SEC-P2-06 mTLS temp-key; SEC-P2-03 parcial (`dps_contract`) |
| 0.3 | 2026-07-30 | Parecer G-SEC-P0 aprovado PO (com ressalva PDF M1); QA EX-* aprovado |
| 0.2 | 2026-07-30 | Hardening code: `xml_safe`, throttle `nf_issue_write`, RLS `issuance_nfartifact`, retry SEFIN, workflow CI security, testes EX-SEC/P1 |
| 0.1 | 2026-07-30 | DoD inicial a partir da análise sênior de segurança NFS-e/SEFIN; anexo NFSE-A / NFSE-OPS |
