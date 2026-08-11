# EXEQ Hub — Plano de Desenvolvimento: Emissor Próprio NFS-e Nacional

| Campo | Valor |
|-------|--------|
| Destinatário | Gestão / direção EXEQ |
| Status | **Autorizado pelo PO** — início liberado |
| Versão do plano | **1.1** (refino pós revisão comitê Tech/PM/Fiscal — 2026-07-29) |
| Data do plano | 2026-07-29 |
| Início | **Imediato** (2026-07-29) |
| PO | Autoriza desenvolvimento conforme este plano |
| Decisão-base | `ADR_NFSE_001_Emissor_Proprio_Nacional.md` (**Aprovado** 2026-07-29) |
| Requisitos | `Exeq_Hub_LLR_Emissor_Proprio_NFSe_Nacional.md` (v0.3) |

---

## 1. Objetivo de negócio

Entregar o **EXEQ Hub como emissor próprio** de **NFS-e no Ambiente Nacional** (SEFIN/ADN), **sem depender** de API comercial de emissão (Focus) no caminho crítico, incluindo:

- Envio da DPS ao governo (mTLS + certificado A1)
- Persistência do **XML** autorizado
- Geração própria do **DANFSe (PDF)** conforme NT 008/2026 v1.02

**Fora deste plano (MVP):** emissão municipal legada, substituição de nota, contencioso, manifestações, integrações Spedy/outros agregadores, NF-e de produto.

**Preservação:** código Focus já existente **permanece** no repositório (lab / **contingência técnica**), sem ser o go-live.

---

## 2. Por que agora

1. Destino estratégico confirmado: **emissor próprio** (gestão + PO).  
2. Focus **não** está em operação — não há “cutover”; o desenvolvimento começa no emissor EXEQ.  
3. A API oficial do governo para gerar DANFSe será **suspensa em 03/08/2026** — o Hub precisa gerar o PDF.  
4. Base técnica já existe no Hub (TaxEngine, fluxo de nota, certificados, artefatos) — reduz retrabalho.

---

## 3. Marcos, buffers e calendário

Início: **29/07/2026**. Capacidade: **1–2 engenheiros sêniores** full-time neste programa.

**Cenário oficial para gestão = Base (com buffers abaixo).** O cenário “otimista” é referência interna, **não** compromisso de gestão.

| Marco | Entrega | Janela-alvo | Buffer | Critério de pronto (mensurável) |
|-------|---------|-------------|--------|----------------------------------|
| **M0 — Kickoff** | Alinhamento | 29–30/07 | — | ADR/LLR lidos; epics criados; donos A/B/NT nomeados; pacote gov baixado |
| **M1 — G-PDF** | DANFSe EXEQ | **até 03/08** (hard) | 0 (data externa) | Ver §3.1 |
| **M2 — Spike SEFIN** | Prova mTLS | 05–12/08 | **+3 dias úteis** se cert/acesso atrasar | Ver §3.1 — **código M2 liberado PO 2026-07-29** (`spike_sefin_mtls`) |
| **M3 — G-EMIT** | 1ª emissão Hub E2E | 19/08–02/09 | **+5 dias úteis** embutidos na faixa | Ver §3.1 |
| **M4 — MVP** | Cancel + QA crítico | 02–16/09 | **+1 semana** de folga no fim da faixa base | Ver §3.1 |
| **M5 — Prod controlada** | Piloto → prod | mid/end set | **+1 semana** | Ver §3.1 + §11 |

### Faixas de confiança (compromisso)

| Cenário | MVP (M4) | Uso |
|---------|----------|-----|
| Otimista | ~início set (~5–6 sem) | Só comunicação interna; **não** prometer à gestão |
| **Base** | **~meio set (~6–8 sem)** | **Compromisso de planejamento** |
| Pessimista | ~fim set / início out (~8–10 sem) | Se dependências externas falharem (§9) |

**Nota de realismo:** M1 em **5 dias corridos** é **agressivo** (NT 008 é densa). Aceitável como *minimum viable PDF* (autorizada + CANCELADA + QR + A4 + campos do XML de fixture), não como pixel-perfect do Anexo I. Ajuste fino de layout continua na Trilha B após 03/08 sem bloquear M2/M3.

### 3.1 Critérios de pronto (aceitação)

| Marco | Aceite objetivo |
|-------|-----------------|
| **M1** | (1) Função/serviço gera PDF a partir de XML NFS-e de fixture; (2) página única ≥ A4 retrato; (3) QR presente; (4) marca d’água CANCELADA em fixture cancelada; (5) `danfse_layout_version=nt008-v1.02`; (6) checklist interno ≥ **80%** dos campos obrigatórios da NT (resto rastreador, não bloqueia M1) |
| **M2** | (1) Handshake mTLS OK em homolog; (2) 1 `POST` com HTTP 2xx e XML/autorização evidenciada; (3) evidência salva (log sanitizado / artefato) |
| **M3** | (1) Criar nota no Hub → status `authorized` no caminho feliz **sem** poll artificial; (2) `NfArtifact` XML + PDF; (3) download Admin; (4) teste unitário mapper/XMLDSig verde |
| **M4** | (1) Cancelamento de nota autorizada → `cancelled`; (2) PDF regenerado com CANCELADA; (3) roteiro QA cobre EX-PRE-01/02, EX-NET-02, EX-FIS-01, EX-PDF-01 — ver `Docs/Exeq_Hub_QA_Roteiro_NFSe_EX_Criticos.md`; (4) Focus ainda no repo e não é default |
| **M5** | (1) Piloto ≥ 1 prestador real em prod controlada **ou** homolog ampliada com 10 emissões; (2) alerta de cert a vencer; (3) runbook SEFIN indisponível; (4) KPIs §15 instrumentados (mesmo que dashboard mínimo) — **aprovado PO Ricardo 2026-07-30** (ver §11.2 / roteiro QA) |

---

## 4. Organização do trabalho (duas trilhas)

```text
                    29/07                         03/08              ~set
Trilha A (Emissão)  |==== spike mTLS ====|==== adapter/DPS ====|==== MVP ====|
Trilha B (DANFSe)   |======== G-PDF ========|==== polish + cancel PDF ========|
```

| Trilha | Foco | Entregáveis |
|--------|------|-------------|
| **A — Emissão** | mTLS, DPS, XMLDSig, FSM sync-first | Adapter `sefin`, mapper, testes, G-EMIT |
| **B — DANFSe** | NT 008 v1.02 | G-PDF + PDF cancelada + versão de layout |

### 4.1 Arquitetura (clareza anti-équívoco)

**Não** criar um app/módulo monólito tipo `fiscal_engine` com Validator+Retry+Artifact+Audit tudo junto.

**Sim** manter fronteiras já existentes e estendê-las:

| Camada | Responsabilidade neste programa |
|--------|----------------------------------|
| `apps.fiscal` | Alíquota, catálogo, RTC/snapshot |
| `apps.issuance` | FSM da nota, orquestração, artefatos |
| `integrations/nfse` | Porta `NfseProvider` + adapter SEFIN + mapper DPS + (cliente mTLS) |
| Gerador DANFSe | Módulo enxuto (ex. `integrations/nfse/danfse` ou `apps/issuance` service) — **só render PDF** a partir do XML |

Isso evita tanto o “Deus objeto” quanto logic de SEFIN espalhada em views.

### 4.2 WBS (governança de backlog)

| Nível | Quando | Conteúdo mínimo |
|-------|--------|-----------------|
| Epics | **Antes / no M0** | `NFSE-A-EMIT`, `NFSE-B-DANFSE`, `NFSE-QA`, `NFSE-OPS` |
| Features / Stories | Sprint planning | Quebrar LLR RF-* / EX-* |
| Tasks / Subtasks | Durante a sprint | Detalhe diário do time |

O plano executivo **não** lista 100 tasks (evita overplanning). Board abre no kickoff com os 4 epics.

---

## 5. Investimento e capacidade

| Item | Necessidade |
|------|-------------|
| Engenharia | 1–2 sêniores (fiscal/integração) M0–M5 |
| Certificado | A1 ICP-Brasil homolog (**bloqueante M2**) |
| Acesso gov | SEFIN/ADN produção restrita |
| Apoio fiscal | Validar XML/PDF amostrais |
| Dono de NT | Revisão **quinzenal** Portal NFS-e |

---

## 6. Matriz de riscos (resumo)

| ID | Risco | P | I | Preventivo | Contingência | Dono |
|----|-------|---|---|------------|--------------|------|
| R1 | Sem G-PDF em 03/08 | M | A | Trilha B prioridade dia 1; MVP PDF 80% | Continuar polish pós-03/08; **nunca** API gov em prod após corte | Tech B |
| R2 | Cert/acesso SEFIN atrasado | M | A | Solicitar no M0 | Deslizar M2/M3 pelo buffer; não fingir G-EMIT | Tech A / Ops |
| R3 | XMLDSig / XSD | A | A | Spike + fixtures | Pair com especialista; golden files | Tech A |
| R4 | SEFIN instável | M | M | Timeout/retry teto | Notas em `failed`/`polling` recuperação; comunicação ops | Tech A |
| R5 | Escopo creep | M | A | PO guarda MVP ADR | Backlog separado; mudança via §13 | PO |
| R6 | NT nova no meio do caminho | M | M | Dono NT quinzenal | Congelar layout versionado; ADR delta | Dono NT |

P = probabilidade (B/M/A)· I = impacto (B/M/A).

---

## 7. Checkpoints para gestão

| Data-alvo | Evidência |
|-----------|-----------|
| 03/08 (M1) | PDF lab (autorizada + CANCELADA) + nota de cobertura ≥80% NT — evidência `.storage/sefin_m1_danfse_coverage.json` |
| ~2ª sem ago (M2) | Evidência autorização homolog SEFIN |
| ~fim ago–início set (M3) | Emitir no Hub → XML/PDF download |
| ~mid set (M4) | Cancelar + PDF cancelada + QA crítico |
| M5 | Parecer go-live / piloto |

---

## 8. Autorizações e ações imediatas

### Já autorizado (PO — 2026-07-29; reconfirmado início imediato 2026-07-29)

- [x] ADR-NFSE-001  
- [x] Início conforme este plano (v1.1)
- [x] M0 — donos: Tech Lead (A∥B∥NT) até nomeação nominal; fábrica iniciada

### Próximos 2 dias úteis (M0)

1. ~~Nomear donos: Trilha A, Trilha B, **NT**, QA.~~ → TL assume A∥B∥NT; QA = testes da entrega  
2. Baixar manuais + **NT 008 v1.02** (contínuo)  
3. Confirmar **A1 homolog** (pedido formal se faltar) — **bloqueia M2**  
4. ~~Criar epics no board.~~ → código iniciado: `danfse` + `sefin` stub  
5. Daily ≤15 min deste programa até M3; **checkpoint execução 30 min** toda sexta com PO.

---

## 9. Matriz de dependências externas

| Dependência | Bloqueia | Owner | Status no kickoff |
|-------------|----------|-------|-------------------|
| Certificado A1 homolog | M2+ | Ops / tenant lab | ☐ |
| Acesso SEFIN/ADN restrita | M2+ | Tech A | ☐ |
| Rede/firewall saída 443 hosts gov | M2+ | Infra | ☐ |
| Pacote docs Portal NFS-e | M0/M1 | Tech B / NT | ☐ |
| Código serviço nacional (catálogo) | M3 qualidade | Fiscal + Hub | ☐ |
| PO disponível p/ escopo | Contínuo | PO | ☑ |

Sem essas linhas verdes, **não** se declara atraso “de engenharia” — declara-se atraso de **dependência**.

---

## 10. Qualidade (QA) — chapter enxuto

| Camada | Obrigatório no MVP | Onde |
|--------|-------------------|------|
| Unitário | Mapper DPS, XMLDSig fixture, map status, gates município/cert, gerador PDF stub | Toda PR de RF |
| Contrato | Golden XML DPS (XSD) | Trilha A |
| Visual/PDF | Checklist NT (M1 80% → M4 95%+) | Trilha B |
| Integração | Adapter stub + 1 fluxo http homolog | M2–M3 |
| Segurança | Sem log de senha/cert; RLS artefato | Contínuo |
| Smoke | Emitir / consultar / cancelar / download | M4+ |
| Carga | **Fora do MVP** | Pós-M5 se volume exigir |

Detalhe de casos: LLR §5 (EX-*). Não duplicar aqui.

---

## 11. Homologação → produção (estágios)

| Estágio | Objetivo | Exit |
|---------|----------|------|
| Lab | Fixtures, PDF, unitários | M1 parcial / M0 |
| Homolog SEFIN | mTLS + 1+ autorizações | M2–M3 |
| Homolog Hub ampliada | Cancel + EX críticos | M4 |
| **Piloto** (1 prestador) | Produção controlada | M5 |
| Produção | Escala gradual | Pós-M5 |

Não pular de lab direto para produção plena.

### 11.1 Atenções de go-live (futuro — não bloquear piloto M5 1 prestador)

Itens já preparados em código/doc; **revalidar antes de escala** (mais de 1 tenant / volume). Checklist de atenção PO + Tech Lead:

| # | Atenção | Evidência / comando | Gate |
|---|---------|---------------------|------|
| GL-01 | **Pentest SEC-P1-09** | Relatório interno `Exeq_Hub_NFSe_Pentest_Report_SEC_P1_09.md` (2026-07-30); F-01 corrigido; externo opcional sob PO | **Interno feito**; externo se escala alta |
| GL-02 | Suite segurança NFS-e verde no ambiente alvo | `pytest apps/issuance/tests/test_security_nfse.py integrations/nfse/tests/test_resilience.py integrations/nfse/tests/test_sefin_mtls.py integrations/nfse/tests/test_dps_contract.py -q` | Regressão obrigatória pré-cutover |
| GL-03 | Resiliência workers (SEC-P2-04) | Time limits Celery ativos; soft limit → `failed`/`SEFIN_TIMEOUT_BUDGET`; ops concurrency baixa sob SEFIN instável (runbook §12.1 item 7) | Confirmar no host de prod |
| GL-04 | Contrato DPS mínimo + mTLS sem PEM residual | `test_dps_contract` + `test_sefin_mtls_cleans_pem_from_disk` | Manter verde no CI |
| GL-05 | Pré-voo ops P0 | `manage.py nfse_g_sec_p0_check` verde; `DEBUG=False`; secrets próprios; `DJANGO_ALLOWED_HOSTS` | Antes de abrir tráfego |

**PO:** marcar data de revisão destes itens no planejamento de escala (pós-M5). Não confundir com aceite do piloto de 1 prestador.

### 11.2 Como o PO valida e aprova o M5

**Objeto da aprovação:** “Piloto M5 autorizado” = 1 prestador em **produção controlada** com ops mínima estável.  
**Não é:** go-live amplo multi-tenant (isso exige §11.1 / pentest).

#### Passo a passo (30–60 min)

| # | O que o PO faz | Evidência / onde olhar | Critério de OK |
|---|----------------|------------------------|----------------|
| 1 | Pedir pacote fresco | Tech: `manage.py nfse_m5_piloto_evidence --tenant agendador-qa` | Arquivo `.storage/sefin_m5_piloto_evidence.json` com `generated_at` do dia |
| 2 | Confirmar tenant piloto | JSON → `piloto_tenant.slug=agendador-qa`, `found=true`, `artifact_count≥1` | Prestador EXEQ; sem misturar smoke/exeq-atibaia na decisão |
| 3 | Confirmar ciclo fiscal | Admin: 1 nota **autorizada** (ou já cancelada) + download **XML** e **PDF**; 1 **cancelamento** com PDF CANCELADA | Cobre §3.1 M5 item (1) na prática |
| 4 | Confirmar alerta de cert | JSON → `settings.cert_beat_task=accounts.scan_expiring_certificates`; ops confirma **Celery beat** up | §3.1 item (2) |
| 5 | Confirmar runbook | Ops declara que leu **§12.1** (parar emissão / sem Focus mágico / escalar >30 min) | §3.1 item (3) |
| 6 | Confirmar KPIs | JSON `piloto_tenant.kpis` + `.storage/sefin_m5_kpis.json` | Números existem (baseline); taxa baixa de auth **não** bloqueia M5 se emit/cancel ok |
| 7 | Confirmar segurança piloto | `nfse_g_sec_p0_check` **no host piloto** com `DEBUG=False` e secrets próprios | Lab local com `DEBUG=True` **não** serve para assinar C5 |
| 8 | Confirmar convênio | `nfse_check_convenio --ibge 3504107 --environment production` → APTO | Município piloto aderente |
| 9 | Assinar | Preencher bloco abaixo (ou mensagem no board: “M5 aprovado PO &lt;data&gt;”) | Status oficial do marco |

#### Bloco de assinatura PO

```
Parecer M5 — Piloto NFS-e EXEQ (produção controlada)
Tenant: agendador-qa · Prestador CNPJ 37229907000137 · IBGE 3504107
Evidência: .storage/sefin_m5_piloto_evidence.json (data: 2026-07-30)
C1 emit/cancel XML+PDF: ☑  C2 beat cert: ☑  C3 runbook §12.1: ☑
C4 KPIs: ☑  C5 g_sec_p0 host piloto: ☑ (postura já aprovada; lab DEBUG N/A)  C6 convênio APTO: ☑
Decisão: ☑ Aprovado  ☐ Aprovado com ressalva: ________________  ☐ Reprovado
PO: Ricardo  Data: 30/07/2026
```

**Status:** **M5 aprovado** (PO Ricardo, 2026-07-30). Escala multi-tenant continua condicionada a §11.1 (GL-01…05).

**Ressalvas aceitáveis no M5:** secrets/`DEBUG` só se o **host piloto real** já estiver OK (lab pode falhar P0-01/02).  
**Não aceitável no M5:** zero nota autorizada/cancelada no piloto; beat ausente; runbook desconhecido da ops.

---

## 12. Contingência e rollback

| Situação | Ação |
|----------|------|
| SEFIN/ADN fora | Não emitir; fila/`failed` controlado; aviso ops; retry depois |
| Cert expirado/revogado | Bloquear emissão (EX-PRE-02); alertar tenant |
| Bug crítico pós-M5 no adapter `sefin` | Feature flag: desligar default `sefin`; **Focus só se reativado explicitamente** (hoje Focus não opera — contingência = **parar emissão** + hotfix, não “ligar Focus magicamente”) |
| PDF falha, XML ok | Manter `authorized`; retry artefato (EX-PDF-01) |
| Regressão grave de layout NT | Fixar `danfse_layout_version`; não misturar templates |

### 12.1 Runbook — SEFIN/ADN indisponível (M5)

Checklist operacional (EX-NET-* no LLR):

1. **Sintomas:** HTTP 5xx/timeout em `POST /dps` ou `GET /nfse/{chave}`; spike/`smoke_sefin_*` falhando; notas em `failed` / `polling`.
2. **Parar emissão nova:** manter `SEFIN_HTTP_MODE=stub` **não** é solução de prod — em prod controlada, **não criar** novas `NfIssue` até recovery; comunicar tenant piloto.
3. **Diagnosticar:**
   - Hosts: `sefin.nfse.gov.br` / `adn.nfse.gov.br` (prod) ou `*.producaorestrita.*` (homolog)
   - Cert A1 do tenant (`purpose=nfse`) válido? (`accounts.scan_expiring_certificates` / Admin)
   - Evidência: `focus_status_raw.http_status`, `rejection_code`, logs `nfse.emit outcome=…`
4. **Não** fallback automático para Focus (RF-51 / §12).
5. **Retry:** após SEFIN saudável, reprocessar notas `failed` elegíveis; novas emissões via Admin/`smoke_sefin_hub_emit`.
6. **Escalar:** se >30 min sem recovery no piloto → PO + ops; registrar incidente.
7. **Workers (SEC-P2-04):** emissão Celery tem `soft_time_limit` / `time_limit` derivados do budget HTTP SEFIN (`NFSE_PROCESS_*_TIME_LIMIT`). Sob 5xx/latência, a task **corta** em vez de prender o worker indefinidamente; nota tende a `failed` / recuperação via reprocesso. Ops: não subir dezenas de workers concurrentes contra SEFIN instável — preferir concurrency baixa no piloto.

**Honestidade operacional:** com Focus fora de operação, o plano B **não** restaura faturamento sozinho até Focus (ou outro) ser religado de propósito. Contingência real até M5 estável = **comunicação + não emitir notas inválidas**.

---

## 13. Mudanças (NTs / legislacao)

- Dono de NT revisa Portal **a cada 15 dias**.  
- Nova NT relevante → ticket `NFSE-NT-*` + impacto (XML / PDF / ambos).  
- Mudança de escopo de produto → decisão PO (não silenciosa na sprint).  
- Layout PDF versionado; nunca sobrescrever versão antiga sem registro.

---

## 14. Governança (RACI enxuto)

| Atividade | PO | Tech Lead | Tech A | Tech B | Dono NT | QA |
|-----------|----|-----------|--------|--------|---------|-----|
| Escopo MVP | A | C | I | I | I | I |
| Trilha emissão | I | A | R | C | C | C |
| Trilha DANFSe | I | A | C | R | C | C |
| Dependências externas | A | C | R | I | I | I |
| Go-live M5 | A | R | C | C | C | R |

R = executa · A = approva · C = consulta · I = informado.

Cadência: daily time box; sexta checkpoint PO 30 min; risco escalado na sexta se ameaça M1/M3/M4.

**Dono de NT (processo):** a cada **15 dias** revisar Portal NFS-e / NT 008; se houver mudança relevante, abrir ticket `NFSE-NT-*` e avaliar impacto em XML/PDF antes de go-live.

---

## 15. KPIs (a partir de M5 / piloto)

Instrumentar cedo, expor depois:

| KPI | Alvo inicial (piloto) | Onde medir |
|-----|----------------------|------------|
| Taxa autorização (authorized / enviadas) | Baseline — meta pós 2 semanas | `manage.py nfse_piloto_kpis` |
| Taxa rejeição fiscal | Classificar códigos top 5 | idem + `rejection_code` |
| % emissões caminho feliz sem poll | ≥ 80% quando SEFIN saudável | idem (`happy_path_no_poll_rate`) |
| p95 geração PDF | &lt; 3 s lab (ajustar com volume) | logs `nfse.pdf_ms=…` |
| Certificados a vencer &lt; 30 dias | 0 sem alerta | beat `accounts.scan_expiring_certificates` + outbox |

Sem dashboard elaborado no MVP — log/métrica mínima basta.
---

## 16. Documentos de referência

| Documento | Uso |
|-----------|-----|
| `ADR_NFSE_001_Emissor_Proprio_Nacional.md` | Decisão |
| `Exeq_Hub_LLR_Emissor_Proprio_NFSe_Nacional.md` | RF/EX |
| `Exeq_Hub_NFSe_Emission_Architecture_Reference.md` | Contexto + addendum |
| `Exeq_Hub_DoD_Seguranca_NFSe_SEFIN.md` | DoD segurança (board NFSE-A / NFSE-OPS) |
| `Exeq_Hub_QA_Roteiro_NFSe_EX_Criticos.md` | Roteiro QA EX-* críticos |
| NT 008 v1.02 | DANFSe |

---

## 17. Mensagem executiva

O EXEQ Hub inicia o **emissor próprio Nacional** com **DANFSe interno**, priorizando o corte federal de PDF em **03/08/2026** (marco M1, PDF mínimo viável). O **compromisso de planejamento** para MVP (emitir, cancelar, XML, PDF) é **~6–8 semanas** (meio de setembro), com buffers entre M2–M5 e rastreio explícito de dependências externas. Arquitetura modular nas camadas já existentes (sem Engine Fiscal monólito). Focus permanece no código como opção técnica futura, **não** como continuidade automática de negócio enquanto estiver desligado. Homologação evolui lab → SEFIN → piloto → produção.

---

## 18. Histórico do plano

| Versão | Data | Nota |
|--------|------|------|
| 1.18 | 2026-07-31 | Ops convênio HTTP multi-IBGE (`nfse_smoke_convenio_http` + doc) |
| 1.17 | 2026-07-31 | Onboarding multi-CNPJ/tenant (`nfse_onboard_tenant` + doc) |
| 1.16 | 2026-07-30 | GL-01 pentest interno + fix Admin IDOR listagem; convênio HTTP ADN com mTLS |
| 1.15 | 2026-07-30 | **M5 aprovado PO Ricardo** — piloto produção controlada (`agendador-qa`) |
| 1.14 | 2026-07-30 | §11.2 roteiro PO validar/aprovar M5; evidência com tenant piloto |
| 1.13 | 2026-07-30 | §11.1 atenções go-live (pentest + suite sec/resiliência/DPS/mTLS) |
| 1.12 | 2026-07-30 | Briefing pentest SEC-P1-09; SEC-P2-04 Celery time limits emissão/poll |
| 1.11 | 2026-07-30 | Ressalva PDF M1 fechada PO; SEC-P2-06 mTLS sem PEM residual; SEC-P2-03 parcial (`dps_contract` no build) |
| 1.0 | 2026-07-29 | Plano inicial autorizado PO |
| 1.1 | 2026-07-29 | Refino: buffers, aceite mensurável, deps, QA, contingência, RACI, KPIs, estágios, arquitetura clarificada |
| 1.2 | 2026-07-30 | M1 polish DANFSe (prod XML); M5 runbook §12.1; KPIs `nfse_piloto_kpis`; beat cert; fix cross-ref §15 |
| 1.3 | 2026-07-30 | Aceite M1 (`danfse_m1_aceite`); QA EX-PRE/NET/FIS/PDF; gate convênio RF-01; evidência M5 |
| 1.4 | 2026-07-30 | Convênio por ambiente (estudo adesão); roteiro QA EX-*; `nfse_check_convenio` |
| 1.10 | 2026-07-30 | Fila pós-M5: Admin IP allowlist, gitleaks CI, regenerar DANFSe Admin, CORS N/A |
| 1.9 | 2026-07-30 | PO reforço: Ops OK; G-SEC-P0 + PDF M1 aprovado c/ ressalva; QA EX-* OK; polish DANFSe pt-BR/espaçamento |
| 1.8 | 2026-07-30 | PO: Ops/QA OK; fix DANFSe cancelada (watermark atrás + Situação Cancelada) |
| 1.7 | 2026-07-30 | PO autorizou `ops.0007` RLS artefato; `nfse_g_sec_p0_check`; `DJANGO_ALLOWED_HOSTS` |
| 1.6 | 2026-07-30 | G-SEC hardening: XXE `xml_safe`, throttle emissão, RLS artefato, retry SEFIN, CI security |
| 1.5 | 2026-07-30 | Anexo DoD segurança NFS-e/SEFIN (board NFSE-A / NFSE-OPS) |

*Detalhe de stories/tasks: sprint planning. Este documento permanece executivo.*
