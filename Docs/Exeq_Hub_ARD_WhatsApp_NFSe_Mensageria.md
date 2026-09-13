# EXEQ Hub — ARD: Canal WhatsApp NFS-e + Mensageria (itens 7–20)

| Campo | Valor |
|-------|-------|
| Tipo | Architecture Review Document (resposta formal da fábrica) |
| Versão | 0.1.0-draft |
| Data | 2026-08-01 |
| Status | **Para aprovação dos gestores** — gate da Fase 3 do canal WhatsApp |
| Complementa | Proposta do canal WhatsApp (canvas 2026-07-31) + análises de IA e persona |
| Base factual | Código do Exeq Hub em 2026-08-01 (`shared/storage`, `apps/ops`, `apps/issuance`, `apps/channel`, RLS) |

Convenção de status usado nas respostas: **Atendido** (já implementado no Hub), **Parcial** (base pronta, falta complemento), **A construir** (escopo novo), **Decisão gestores** (não é técnico).

---

## 7. Armazenamento dos documentos fiscais

**Decisão registrada:** PDF e XML armazenados no EXEQ Hub, com consulta pelo prestador e reenvio ao tomador no período de retenção.

**Situação no Hub:** abstração de storage única (`shared/storage`, `get_storage()`) com backend **filesystem local** implementado; todo arquivo é indexado por `StoredFile` (chave, checksum, tamanho, propósito) e vinculado à nota por `NfArtifact`. S3/MinIO já previstos como choices do modelo, sem backend implementado.

**Resposta da fábrica:**

- **Onde:** produção com storage **S3-compatível (MinIO auto-hospedado ou bucket gerenciado)**; desenvolvimento continua em filesystem. Justificativa: a abstração existente torna a troca um adaptador único; S3-compatível entrega redundância, versionamento e criptografia server-side sem código de aplicação.
- **Backup:** bucket com versionamento + replicação para segunda região/host; banco cobre o índice (`StoredFile`).
- **Redundância:** nativa do backend escolhido (replicação MinIO ou durabilidade do provedor).
- **Versionamento:** documento fiscal é **imutável** — nunca sobrescrevemos; retificação/substituição gera novo `StoredFile` e novo vínculo. Versionamento do bucket é proteção adicional contra deleção acidental.
- **Recuperação de perda:** o XML é recuperável no ADN/SEFIN (a nota autorizada existe no ambiente nacional) e a DANFSe é **re-renderizável a partir do XML** pelo gerador interno já homologado. Perda de arquivo não é perda fiscal; o plano de recuperação é re-materializar a partir da fonte autorizativa.
- **Crescimento estimado:** DANFSe ~100 KB + XML ~15 KB por nota. Cliente com 30 notas/mês ≈ **3,5 MB/mês (~42 MB/ano)**. 1.000 clientes ≈ ~42 GB/ano. Custo de storage é desprezível frente à mensageria (ver §17).

**Status:** Parcial — falta o adaptador S3/MinIO e a rotina de replicação (estimativa: 3–5 dias).

---

## 8. Política de retenção dos documentos

**Decisão registrada:** disponíveis durante contrato ativo; +12 meses após encerramento; depois, expurgo definitivo; solicitações posteriores direcionadas ao contador/sistema de escrituração.

**Resposta da fábrica:**

- **Expurgo automático:** job mensal (Celery Beat, infra já existente) que identifica tenants com contrato encerrado há mais de 12 meses e remove artefatos + arquivos, registrando o expurgo em auditoria.
- **Arquivamento:** antes do expurgo, opção de exportação em lote (ZIP por competência) entregue ao cliente/contador — recomendado como etapa obrigatória do offboarding.
- **Impacto financeiro:** retenção de 12 meses pós-contrato custa centavos por cliente (ver estimativa §7); não é fator de decisão.
- **Retenção configurável por plano:** viável com um campo `retention_months` por tenant/plano lido pelo job de expurgo. Recomendação: adotar desde o início — vira diferencial comercial sem custo técnico relevante.
- **Ressalva de compliance (obrigatória em contrato):** a obrigação legal de guarda dos documentos fiscais (5 anos) é **do prestador**; o Hub é cópia de conveniência. O contrato e o offboarding devem deixar isso explícito.

**Status:** A construir (job de expurgo + exportação de offboarding) · Decisão gestores (retenção por plano e texto contratual).

---

## 9. Auditoria operacional

**Situação no Hub — trilha já existente:**

| Evento exigido | Onde é registrado hoje |
|---|---|
| Emissão da NFS-e (timeline completa de status) | `NfIssueEvent` |
| Geração de PDF / XML | `NfArtifact` + `StoredFile` (checksum, timestamp) |
| Envio ao WhatsApp + confirmação de envio | `ChannelNotification` (status sent/failed, `provider_ref`) |
| Erro de envio / reprocessamentos / retries | `OutboxMessage` (attempts, last_error, correlation_id) |
| Webhooks recebidos | `WebhookInbox` |
| Operações com certificado A1 | `CertificateAudit` |

**Gaps a construir:** confirmação de **entrega** (depende do webhook de status da Evolution/Meta — Fase 3), registro de **download pelo usuário**, **reenvio manual** e **acionamento de fallback**. Todos são eventos novos nas tabelas existentes, não um subsistema novo.

**Resposta às definições pedidas:** estrutura relacional (não log solto) com `tenant` + `correlation_id` em todos os registros; retenção igual à do documento (item 8); consulta via Admin e API autenticada; impacto de armazenamento desprezível (linhas de bytes vs. PDFs de KB).

**Status:** Parcial — base forte, 4 eventos a adicionar.

---

## 10. Criptografia dos documentos

**Situação no Hub:** chave privada A1 (PFX) e segredos de tenant (`TenantSecret`) já criptografados com **Fernet** em repouso; mTLS com SEFIN/ADN; TLS na borda da API.

**Resposta da fábrica:**

- **Em trânsito:** TLS 1.2+ em toda borda; mTLS com SEFIN (feito). **Atendido.**
- **Em repouso — segredos:** Fernet (feito). Pendência já em backlog: eliminar a chave de fallback de desenvolvimento e mover a chave para Vault/Secrets Manager (**SEC-P2-01**).
- **Em repouso — banco:** criptografia de disco/volume do host (LUKS ou equivalente do provedor). TDE nativo não existe no PostgreSQL comunitário; criptografia por coluna além dos segredos não se justifica com RLS ativo.
- **Em repouso — arquivos PDF/XML:** criptografia **server-side do bucket (SSE)** quando o storage S3-compatível entrar (item 7). Justificativa para **não** criptografar por arquivo na aplicação: adicionaria gestão de chave por documento e quebraria re-render/streaming, sem ganho real sobre SSE + RLS + controle de acesso — o conteúdo da NFS-e é, por definição, documento com validade pública verificável no ambiente nacional.
- **Rotação de chaves:** Fernet suporta `MultiFernet` (rotação sem re-criptografia em massa imediata); processo formal de rotação entra junto com SEC-P2-01.

**Status:** Parcial — segredos atendidos; SSE de arquivos depende do item 7; Vault/rotação já são backlog SEC-P2-01/02.

---

## 11. Autenticação de acesso aos arquivos

**Situação no Hub:** download hoje só por Admin autenticado (com isolamento por membership, corrigido no pentest GL-01); API do Hub com autenticação e escopo de tenant; **nenhuma URL pública de artefato existe** — decisão deliberada de segurança.

**Resposta da fábrica:**

- **Canal WhatsApp:** entrega por **anexo** (decisão já recomendada) — não cria superfície de URL pública.
- **Portal/consulta posterior:** endpoint autenticado (sessão/JWT do Hub) com verificação de tenant + RLS; streaming pelo backend, sem link direto ao storage.
- **Se link externo for exigido no futuro:** signed URLs com expiração ≤ 15 minutos, emitidas sob autenticação, com revogação por rotação da chave de assinatura.
- **Compartilhamento indevido:** um arquivo entregue (anexo ou download) é cópia fora do nosso controle — em qualquer arquitetura. A mitigação real é não manter links permanentes e registrar cada acesso (item 9).

**Status:** Atendido no desenho; endpoint de portal a construir junto do canal.

---

## 12. Escalabilidade da consulta

**Decisão registrada:** consulta dos últimos 12 meses **ou** últimas 24 notas em até 24 meses; além disso, direcionar ao contador. A fábrica recomenda a primeira opção (12 meses) por ser mais simples de comunicar e implementar.

**Resposta da fábrica:** a API já é paginada (`HubPageNumberPagination`) e indexada por tenant/status; adicionar índice composto por competência quando a consulta histórica entrar. Cache não se justifica no volume projetado (consultas por tenant são pequenas e o Postgres resolve com índice). Custo: artefatos antigos podem migrar para classe de storage frio, transparente à aplicação.

**Status:** Parcial — falta apenas o filtro por período na API e o índice; esforço de 1–2 dias.

---

## 13. Idempotência

**Situação no Hub — já é padrão da casa, em todas as camadas:**

- Emissão: `create_nf_issue` idempotente por `(tenant, idempotency_key)` — retry não duplica nota.
- Entrada WhatsApp: `ChannelSession` deduplica por `phone:message_id` + debounce de 5 s.
- Webhooks: `WebhookInbox` para deduplicação de callbacks.
- Fila: `OutboxMessage` com claim transacional (`select_for_update`) — dois workers não despacham a mesma mensagem.
- DAS: chave natural dupla `(tenant, provider, tipo, competência, versão)`.

**Complemento para o canal:** usar o **message id nativo da Evolution/Meta** como chave de deduplicação do webhook real (o desenho atual já usa `message_id`; na Fase 3 passa a ser o id nativo). Timeout+retry do cliente WhatsApp cai na mesma chave — sem duplicidade.

**Status:** Atendido — estratégia definida e implementada; só a chave do payload nativo muda na Fase 3.

---

## 14. Disaster Recovery

**Situação no Hub:** arquitetura favorável a DR (banco como fonte de verdade + outbox com replay), mas **sem tooling formal de backup hoje** — gap real e assumido.

**Plano proposto (a formalizar com os gestores):**

| Falha | Estratégia | Efeito na operação |
|---|---|---|
| PostgreSQL | Backup diário + arquivamento WAL (PITR). **RPO ≤ 15 min, RTO ≤ 4 h** (alvos propostos) | Fonte de verdade; prioridade máxima |
| Redis | Tratado como efêmero — broker Celery. Sem backup | Tarefas perdidas são reenfileiradas a partir do outbox (varredura periódica já existe) |
| Storage de PDFs | Bucket versionado + replicação; re-materialização pelo XML do ADN (item 7) | Sem perda fiscal |
| Meta/Evolution indisponível | Retry com backoff até 8 tentativas → DLQ (`dead`); emissão **não** é afetada (item 20) | Mensagens atrasam, notas continuam saindo |
| SEFIN indisponível | Retries + time limits Celery + runbook §12.1 do Plano (aprovado no M5): parar emissão, escalar >30 min | Procedimento já homologado |
| Servidor | Recriação por Docker Compose + restore de banco e bucket | RTO dentro das 4 h |

**Replay de filas:** o outbox é persistente no banco — após restore, mensagens `pending`/`failed` são redispachadas pela varredura; `dead` são reprocessáveis manualmente (item 20).

**Status:** A construir (tooling de backup + teste de restore documentado) · Decisão gestores (aprovar RPO/RTO).

---

## 15. Multitenancy

**Situação no Hub — requisito crítico já endereçado em profundidade:**

- **Row-Level Security nativo do PostgreSQL** com `FORCE ROW LEVEL SECURITY` e política `tenant_isolation` em 22 tabelas — o isolamento vale mesmo para SQL direto, não só para o ORM.
- `TenantOwnedModel` + middleware de contexto de tenant em toda a camada de aplicação.
- Admin filtrado por membership (achado do pentest GL-01, corrigido e testado).
- Arquivos segregados por tenant na chave de storage; credenciais por tenant criptografadas (`TenantSecret`).

**Complementos para o canal WhatsApp:** instância Evolution/WABA **por prestador** (decisão da proposta — credencial e número segregados por tenant); logs estruturados com `tenant_id` obrigatório (a padronizar na Fase 3). Fila única hoje com payloads escopados por tenant — segregação física de filas só se um tenant de alto volume degradar os demais (não é o caso projetado; reavaliar em escala).

**Status:** Atendido no núcleo; complementos de canal na Fase 3.

---

## 16. Compliance fiscal — rastreabilidade

**Resposta da fábrica — cadeia de identificadores correlacionados, já existente do lado fiscal:**

```
Solicitação (idempotency_key / ChannelSession)
  → NfIssue (id, idempotency_key)
    → NfIssueEvent (timeline: DPS enviada, autorização, erros)
    → identificadores SEFIN (nDPS, chave de acesso da NFS-e)
      → NfArtifact PDF/XML → StoredFile (checksum SHA)
        → OutboxMessage (correlation_id, tentativas)
          → ChannelNotification (provider_ref da mensagem WhatsApp)
```

Cada elo responde a uma pergunta do auditor: *DPS enviada?* (`NfIssueEvent`), *autorizada?* (chave de acesso + evento), *PDF/XML íntegros?* (checksum do `StoredFile`), *entregue?* (`ChannelNotification` + confirmação de entrega do item 9).

**Gap:** o elo final (confirmação de **entrega** pelo provedor de mensageria) entra na Fase 3 com o webhook de status. Até lá, o comprovante é o aceite de envio (`provider_ref`).

**Status:** Parcial — cadeia fiscal completa; elo de entrega na Fase 3.

---

## 17. Custo operacional (estimativa)

Premissas: 30 notas/cliente/mês; ~115 KB por nota (PDF+XML); infraestrutura em VPS gerenciada; Evolution API auto-hospedada. **Valores de planejamento, a validar com cotações antes da Fase 3.**

| Item | 100 clientes | 500 | 1.000 | 5.000 |
|---|---|---|---|---|
| Compute (app+workers+Postgres+Redis) | R$ 300–500 | R$ 800–1.200 | R$ 1.500–2.500 | R$ 6.000–10.000 |
| Storage + backup (acumulado ano 1) | < R$ 20 | < R$ 60 | ~R$ 120 | ~R$ 600 |
| Evolution API (host dedicado) | R$ 100–200 | R$ 200–400 | R$ 400–800 | R$ 1.500–3.000 |
| Observabilidade (Sentry + métricas) | R$ 0–150 | R$ 150–300 | R$ 300–500 | R$ 800–1.500 |
| E-mail transacional (fallback) | < R$ 50 | < R$ 100 | ~R$ 150 | ~R$ 500 |
| **Total mensal (ordem de grandeza)** | **R$ 0,5–1 mil** | **R$ 1,3–2 mil** | **R$ 2,5–4 mil** | **R$ 9–15,5 mil** |

Notas: (1) custo por cliente **cai** com escala (R$ 5–10 → R$ 2–3); (2) se a mensageria migrar para a **Cloud API oficial da Meta**, somar custo por conversa (~R$ 0,04–0,50) — decisão de canal com impacto direto de custo e de risco de bloqueio (API não oficial); (3) IA conversacional, se aprovada, adiciona centavos por conversa (análise anterior).

**Decisão PO (2026-08-01): suportar os dois provedores.** Implementado gateway dual em `integrations/whatsapp/gateway.py`: Evolution (não oficial, custo zero/msg) e Meta Cloud API oficial (`integrations/meta_cloud/`), com seleção global (`WHATSAPP_PROVIDER`) e override por tenant (`tenant.settings["whatsapp_provider"]`). Cada `ChannelNotification` registra o provedor usado — base para custeio por conversa e migração gradual por cliente.

**Fase 2 (2026-08-01):** `send_media` nos dois provedores + `deliver_nf_artifacts` no outbox `nf_issue.authorized` — PDF (DANFSe) e XML anexados ao solicitante da `ChannelSession`; falha de mídia não reemite a nota (retry/DLQ do outbox).

**Fase 3 (2026-08-01):** webhook fail-closed com `EVOLUTION_WEBHOOK_TOKEN` (header); payload nativo Evolution com tenant via `settings.evolution_instance` (ignora `tenant_slug` spoofado); throttle `webhook_evolution`; CPF/telefone mascarados em log.

**Status:** Decisão tomada e implementada (camada de envio) — validar premissas de custo com cotações reais.

---

## 18. Observabilidade

**Situação no Hub:** métricas de negócio via ORM (`apps/issuance/metrics.py`), comandos de evidência ops (`nfse_g_sec_p0_check`, `nfse_m5_piloto_evidence`), logs de aplicação. **Sem Prometheus/Grafana/Sentry hoje** — adequado ao piloto de 1 prestador, insuficiente para escala.

**Proposta da fábrica (pré-requisito de escala, junto com GL-02/03/05):**

- **Erros:** Sentry (captura de exceções app + workers).
- **Métricas/dashboards:** django-prometheus + Grafana (ou stack equivalente leve): profundidade das filas outbox/Celery, latência SEFIN, taxa de erro por integração (SEFIN, ADN, Evolution), saúde de workers.
- **Alertas mínimos:** outbox `dead` > 0; fila `pending` acima de limiar; taxa de falha SEFIN > X%; certificado A1 expirando (já existe verificação agendada); Evolution sem resposta.
- **Indicadores pedidos** — todos deriváveis dos modelos existentes, sem instrumentação nova: tempo emissão→entrega (`NfIssue.created_at` → `ChannelNotification`), taxa de sucesso/retry/falha (`OutboxMessage.attempts/status`), documentos pendentes (notas autorizadas sem notificação enviada).

**Status:** A construir (~1 semana de setup) — recomendado antes de qualquer escala, independentemente do canal WhatsApp.

---

## 19. SLA operacional (alvos propostos)

| Medição | Alvo proposto | Observação |
|---|---|---|
| Emissão (aceite SEFIN) | p95 < 60 s | Depende do ambiente nacional; time limits Celery já protegem o worker |
| Geração PDF/XML pós-autorização | p95 < 10 s | Processo interno, sem dependência externa |
| Envio WhatsApp pós-artefato | p95 < 60 s | Fila outbox em operação normal |
| Fallback (e-mail/portal) | Acionado após esgotar 8 tentativas (~30–40 min) | Política atual do dispatcher |
| Disponibilidade da plataforma | 99,5% mensal | Compatível com topologia atual (host único). 99,9% exige redundância — decisão de custo |
| Recuperação (RTO) | ≤ 4 h | Vinculado ao plano de DR (item 14) |

**Status:** Decisão gestores — aprovar alvos; medição entra com a observabilidade (item 18).

---

## 20. Desacoplamento emissão fiscal × mensageria

**Resposta da fábrica: este é exatamente o padrão já implantado no Hub** — o requisito está atendido por arquitetura, não por promessa:

1. **Processo fiscal** (síncrono no domínio): recebimento → validação → emissão SEFIN → autorização → geração e persistência de PDF/XML. Termina aqui, com a nota autorizada e os artefatos gravados. **Nenhuma etapa consulta ou espera o WhatsApp.**
2. **Processo de comunicação** (assíncrono): o evento (`nf_issue.authorized`, futuramente com destino ao tomador) é gravado na **tabela outbox na mesma transação** do fato fiscal; um dispatcher independente entrega via Evolution com retry/backoff exponencial até 8 tentativas; após isso a mensagem vai para `dead` (**DLQ nativa**), reprocessável manualmente. Varredura periódica garante que nada fica esquecido.

Indisponibilidade da Meta/Evolution: mensagens acumulam e são reentregues; **nenhuma nota é reemitida ou perdida**. Garantia de entrega: *at-least-once* na fila + deduplicação no consumidor (idempotência, item 13) = sem duplicidade efetiva.

**Gaps declarados:** (a) **fallback por e-mail não existe** — o Hub não tem capacidade de envio de e-mail hoje; entra como escopo da Fase 2/3 do canal (provedor transacional + template); (b) reprocessamento de `dead` é manual sem interface dedicada — adicionar ação de replay no Admin.

**Status:** Atendido no núcleo · A construir: fallback e-mail + replay de DLQ no Admin.

---

## Consolidação e gate da Fase 3

| Item | Tema | Status |
|------|------|--------|
| 7 | Armazenamento | Parcial — adaptador S3/MinIO a construir |
| 8 | Retenção | A construir (expurgo/offboarding) + decisão de plano |
| 9 | Auditoria | Parcial — 4 eventos a adicionar |
| 10 | Criptografia | Parcial — SSE arquivos + Vault (SEC-P2-01 já em backlog) |
| 11 | Autenticação de arquivos | Atendido no desenho |
| 12 | Escalabilidade consulta | Parcial — filtro período + índice (1–2 dias) |
| 13 | Idempotência | **Atendido** |
| 14 | Disaster Recovery | A construir (backup/restore) + aprovar RPO/RTO |
| 15 | Multitenancy | **Atendido** no núcleo (RLS 22 tabelas) |
| 16 | Compliance fiscal | Parcial — elo de entrega na Fase 3 |
| 17 | Custo | **Decidido PO 2026-08-01** — gateway dual Evolution + Meta implementado; premissas de custo a validar |
| 18 | Observabilidade | A construir (~1 semana) — pré-requisito de escala |
| 19 | SLA | Decisão gestores (alvos propostos) |
| 20 | Desacoplamento | **Atendido** por arquitetura + fallback e-mail a construir |

**Decisões que os gestores precisam aprovar para liberar a Fase 3:** RPO/RTO (14), alvos de SLA (19), premissas de custo e canal Meta oficial vs. Evolution não oficial (17), retenção por plano e texto contratual de guarda fiscal (8).

**Compromissos técnicos que a fábrica assume antes/durante a Fase 3:** adaptador S3/MinIO + SSE (7/10), backup/PITR com teste de restore (14), observabilidade mínima (18), eventos de auditoria complementares (9), fallback e-mail + replay DLQ (20).

| Versão | Data | Mudança |
|--------|------|---------|
| 0.1.0-draft | 2026-08-01 | Resposta formal da fábrica aos itens 7–20 da revisão arquitetural do PO |
| 0.2.0 | 2026-08-01 | Item 17 decidido (PO): gateway dual WhatsApp — Evolution + Meta Cloud API — implementado com seleção por tenant e provedor auditado por notificação |
