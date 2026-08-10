# EXEQ Hub — U3 NF-e SEFAZ-SP · Tickets I1–I8

| Campo | Valor |
|-------|--------|
| Tipo | Backlog de engenharia (fábrica) |
| Base | ADR-NFE-001 · LLR domínio 0.1 · análise TL 2026-08-05 |
| Gate alvo | **G-NFE-SPIKE** → **G-EMIT-NFE** |
| Policy PR | 1 ticket = 1 PR · só `apps/nfe`, `integrations/sefaz_nfe`, frontend nfe, docs nfe · **G-IMPACT-OK** no I8 |
| Esforço | S=0.5–1d · M=1–2d · L=2–4d · XL=4–6d (1 dev sênior; buffer SEFAZ à parte) |

---

## Mapa

| ID | Título | Esforço | Depende | Gate |
|----|--------|---------|---------|------|
| **I1** | Artefatos XML (persist + download) | M | — | foundation | **done** |
| **I2** | DANFE PDF a partir do XML | M | I1 | G-EMIT | **done** |
| **I3** | Endurecimento XML NFe 4.00 happy-path SP | L | — (// I1) | G-SPIKE | **done** |
| **I4** | Emissão HTTP robusta (parse cStat + raw) | L | I3 ideal | G-SPIKE / G-EMIT | **done** |
| **I5** | Consulta / poll de recibo | M | I4 | G-EMIT | **done** |
| **I6** | Cancelamento evento 110111 | L | I1, I4 | G-EMIT | **done** |
| **I7** | Command spike + evidências homolog | S–M | I3, I4 | **G-NFE-SPIKE** | **done** |
| **I8** | UI downloads + G-IMPACT smoke NFS-e | M | I1–I2 | **G-EMIT-NFE** + G-IMPACT | **done** |

Ops paralelo (não bloqueia I1–I2–I3): **IE-SP + credenciamento homolog** (bloqueia só SPIKE real / G-EMIT).

---

## I1 — Artefatos XML

**Objetivo:** Persistir XML pós-autorização (e espelho cancel futuro) e download multi-tenant seguro. `download_xml` só se artefato existir (não mentir em `allowed_actions`).

**Escopo**
- Model `NfeArtifact` (`xml_authorized` | `xml_cancel` | `danfe_pdf`) + `StoredFile`
- Service `ensure_authorized_xml` / store idempotente
- Emit stub/HTTP: grava XML quando `authorized` (stub: `build_nfe_xml` do snapshot)
- `GET /api/v1/nfe/invoices/{id}/artifacts/xml`
- Admin opcional; sem PDF (I2)

**Fora:** DANFE, e-mail outbox, cancel SEFAZ

**Critérios de PR**
- [ ] Migration com unique (invoice, kind)
- [ ] Unit: store idempotente; download 200 tenant correto; 404 sem artefato / cross-tenant
- [ ] `allowed_actions` inclui `download_xml` só com XML
- [ ] pytest verde; zero mudança `issuance` SEFIN

**Status:** **done** (código + testes 2026-08-05)

---

## I2 — DANFE PDF

**Objetivo:** PDF EXEQ a partir do XML; falha PDF **não** reverte `authorized` (D-10).

**Escopo:** gerador DANFE (lib leve) · kind `danfe_pdf` · `GET .../artifacts/pdf` · flag `pdf_pending` se falhar

**Critérios de PR:** unit render mínimo (chave/emitente) · EX-PDF-01 · `download_pdf` condicional

**Status:** **done** (render + store + D-10 + testes 2026-08-05)

---

## I3 — XML NFe 4.00 (happy path SP)

**Objetivo:** Reduzir rejeição schema/regra em homolog SN CSOSN 102 + CRT1.

**Escopo:** revisar `xml_nfe.py` (ide, emit, dest, det, total, transp, pag) · testes golden XML · opcional validação XSD se repo tiver schema

**Critérios de PR:** testes fixture SP · sem network · changelog do que ainda pode rejeitar SEFAZ

**Status:** **done** (homolog dest, idDest, arredondamento vUn/qCom, headers snapshot; 2026-08-05)

**Notas residual SEFAZ (ainda possíveis em homolog):**
- IE emitente inválida ou credenciamento ausente
- NCM / CFOP / CST fora do catálogo da operação
- Cert A1 / mTLS / SOAP binding
- Regras estaduais adicionais não cobertas no happy path

---

## I4 — Emissão HTTP robusta

**Objetivo:** SOAP autorizacao com parse cStat/protNFe/xMotivo estável; raw sanitizado no event.

**Escopo:** melhorar `transport`/`port` · injetar XML assinado no artifact flow · dry_run ainda válido · status rejected/failed/polling corretos

**Critérios de PR:** unit parse com XML resposta fixture · mock `requests.post` · cert missing → CERT

**Status:** **done** (parse infProt>lote, sanitize raw, signed_xml→artefatos, mock POST; 2026-08-05)

**Fora (explícito):** I5 consultar/recibo, I6 cancel 110111, I7 spike command, worker assíncrono emit (RNF-05), multi-UF, NfeTransmissionAttempt model

## I5 — Poll / consultar

**Objetivo:** `NfeProvider.consultar` + task/reconciliação para `polling` → authorized|rejected|failed.

**Escopo**
- Parse `nRec` (lote 103) + ret `consultar` (retAutorização / consulta protocolo)
- `poll_nfe_invoice` + task Celery; `schedule` após emit → polling
- Teto `NFE_POLL_MAX_ATTEMPTS` → `failed` + log alerta (FSM-05)
- Sem reentrada de série; `number_consumed` permanece True

**Fora:** I6 cancel, I7 spike, UI, worker assíncrono de emit (RNF-05)

**Critérios de PR:** unit transição FSM · sem reentrada de número · timeout → failed + alerta opcional

**Status:** **done** (consultar + poll + teto + testes 2026-08-05)

---

## I6 — Cancel 110111

**Objetivo:** Evento cancel assinado + SEFAZ; `xml_cancel` + estado `cancelled`.

**Escopo**
- Build `envEvento` 110111 + assinatura `infEvento`
- HTTP `NFeRecepcaoEvento4`; parse retEvento (cStat 135 → cancelled)
- Persist `xml_cancel`; stub lab continua cancelar
- Justificativa 15–255; falha SEFAZ → volta `authorized`

**Fora:** I7 spike, UI, CCe, inutilização

**Critérios de PR:** unit build evento · mock HTTP cancel · stub continua a cancelar em lab · justificativa 15–255

**Status:** **done** (evento 110111 + artefato + testes 2026-08-05)

---

## I7 — Spike command

**Objetivo:** `manage.py nfe_spike_sefaz` (tenant, cnpj, dry-run/http) + saída auditável (cStat, sem secrets).

**Escopo**
- Command `nfe_spike_sefaz`: stub | http | `--dry-run`
- Evidence JSON (`.storage/nfe_spike_evidence.json`); `g_spike_candidate` se authorized HTTP homolog
- Sem rede em stub/dry_run (cert may fail dry-run before POST — esperado)

**Critérios de PR:** command em stub/dry_run sem rede · doc 5 linhas no help · evidência quando homolog OK → marca G-SPIKE

**Status:** **done** (command + testes stub 2026-08-05)

**G-NFE-SPIKE homolog real:** only when ops runs `--mode http` without dry-run and gets cStat 100 — then set gate with evidence file.

---

## I8 — UI + G-IMPACT

**Objetivo:** Botões real download no Hub; smoke NFS-e no release; não habilitar `NFE_ENABLED` prod sem gate.

**Escopo**
- Hub NF-e: botões XML/DANFE via `allowed_actions` → `GET .../artifacts/xml|pdf` (`hub-nfe.js`)
- `manage.py nfe_g_impact_nfse_smoke` — 1 NFS-e stub authorized; `NFE_ENABLED` permanece off no smoke
- Release note abaixo; flag default off (`settings.NFE_ENABLED`)

**Critérios de PR:** UI chama endpoints I1/I2 · checklist G-IMPACT (1 emit NFS-e stub ou smoke script) · nota de release

**Status:** **done** (UI downloads + smoke command + testes 2026-08-05)

### Nota de release U3 I7–I8

| Item | Valor |
|------|--------|
| Flags | `NFE_ENABLED=false` default; não ligar prod multi-tenant sem G-EMIT-NFE |
| Spike | `python manage.py nfe_spike_sefaz --tenant <slug> --cnpj <cnpj> --mode stub` |
| G-IMPACT | `python manage.py nfe_g_impact_nfse_smoke --tenant <slug>` exit 0 |
| UI | Lista/detalhe: Baixar XML / DANFE se `download_*` em `allowed_actions` |
| Homolog SEFAZ | IE + A1 + `--mode http` → se authorized, anexar evidence e marcar G-NFE-SPIKE |

---

## Sequência sugerida de PRs

```text
I1 ──► I2 ──► I8 (UI parcial após I1 ok)
 │
I3 ──► I4 ──► I5
         └──► I6
I3+I4 ──► I7 (SPIKE)
I1…I7 ──► I8 full (G-EMIT + IMPACT)
```

---

## DoD onda U3

1. G-NFE-SPIKE (I7 + homolog ops)  
2. G-EMIT-NFE: authorized + XML + DANFE em SP homolog  
3. Cancel simples homolog  
4. G-IMPACT-OK  
5. Feature flag default off em multi-tenant prod  
