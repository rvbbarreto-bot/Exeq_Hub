# Checklist — Homologação AN (NF-e de Entrada)

Use este roteiro em **homologação** (`tp_amb=2`) antes de liberar produção.

## Setup

- [ ] `NFE_ENTRADA_ENABLED=true`
- [ ] `tenant.settings.nfe_entrada_enabled=true`
- [ ] `NFE_ENTRADA_HTTP_MODE=http`
- [ ] Certificado A1 válido (`purpose=nfe`) para CNPJ destinatário
- [ ] Provider ativo com CNPJ = destinatário das NF-e de teste
- [ ] Celery worker + beat (se testar automático)

## Distribuição DFe (distNSU)

- [ ] **H1** — Primeira consulta: cursor criado (`ultNSU`, `maxNSU`, `last_c_stat`)
- [ ] **H2** — cStat **137** quando não há documentos novos
- [ ] **H3** — cStat **138** quando há lote; documentos em `NfeEntradaDocument`
- [ ] **H4** — NSU persistido; segunda consulta idempotente (sem duplicatas)
- [ ] **H5** — cStat **656** preenche `blocked_until`; consulta seguinte respeita bloqueio
- [ ] **H6** — `NfeDistribuicaoSyncLog` com `correlation_id`, duração, contagem

## Documentos

- [ ] **H7** — resNFe: `xml_status=pending`, metadados emitente/chave/valor
- [ ] **H8** — procNFe (quando AN enviar): `xml_status=available`, download OK
- [ ] **H9** — Hash SHA-256 (`xml_hash`) bate com arquivo armazenado

## Manifestação destinatário

- [ ] **H10** — 210210 Ciência: `status=accepted`, `manifest_status=ciencia`
- [ ] **H11** — Idempotência: segundo envio não duplica accepted
- [ ] **H12** — 210200 Confirmação: **só** com confirmação explícita (Hub/API)
- [ ] **H13** — 210220 Desconhecimento: confirmação explícita
- [ ] **H14** — 210240 Não realizada: justificativa ≥ 15 caracteres
- [ ] **H15** — XML do evento assinado persistido (`stored_file` manifestação)

## Hub V4

- [ ] **H16** — Lista: KPIs, filtros manifestação/XML, cursor NSU
- [ ] **H17** — Detalhe: chave, emitente, ações manifestação coerentes
- [ ] **H18** — Config: `automatic_enabled` + intervalo salvos
- [ ] **H19** — Sidebar "NF-e de Entrada" visível com flag

## API REST

- [ ] **H20** — `GET /nfe/entrada/` com filtros e KPIs
- [ ] **H21** — `POST /nfe/entrada/sync/` → 202
- [ ] **H22** — `PUT /nfe/entrada/distribution/config/`
- [ ] **H23** — `POST /nfe/entrada/{id}/manifest/`
- [ ] **H24** — `GET /nfe/entrada/{id}/xml/` (quando available)

## Segurança / multi-tenant

- [ ] **H25** — Tenant B não acessa documentos do tenant A (API + Hub)
- [ ] **H26** — Papel readonly não executa sync/manifestação (WRITE_ROLES)

## Evidências a arquivar

| Item | Onde |
|------|------|
| Log sync | `NfeDistribuicaoSyncLog` |
| XML NF-e | Storage `nfe_entrada/{tenant}/{provider}/` |
| XML evento | Storage `nfe_entrada/{tenant}/manifest/` |
| Print Hub | Lista + detalhe pós-ciência |
| OpenAPI | `/api/v1/openapi.json` paths `/nfe/entrada/*` |

**Responsável:** _______________ **Data:** _______________ **Resultado:** ☐ Aprovado ☐ Pendente
