# Índice da documentação oficial EXEQ Hub

Repositório: https://github.com/rvbbarreto-bot/Exeq_Hub

| Doc | Arquivo canônico | Status |
|-----|------------------|--------|
| Contrato | `EXEQ Hub - Contrato de Desenvolvimento da Plataforma.docx` | Ativo |
| v1 Domínio | `Exeq_Hub_v1_Business_Domain_Functional_Specification.md` | **1.1.0 promovido** |
| v2 Arquitetura | `Exeq_Hub_v2_Platform_Architecture_Engineering_Guide.md` | **2.1.0 expandido** |
| v3 DER | `Exeq_Hub_v3.1_Database_Design_ERD.md` (+ `.docx`) | **3.1.2** (amend SCHEDULING + FOOD) |
| ADR Agendamento | `ADR_SCHED_001_Agendamento_Exeq_Hub.md` | **Aprovado** (PO 2026-07-28) |
| ADR Hub Food V1 | `ADR_FOOD_001_Exeq_Hub_Food_V1.md` | **Aprovado + GO Sprint 1** (PO 2026-08-09) |
| Estudo split Agendador | `Exeq_Agendador_Split_Payment_Estudo_Arquitetura.md` | Estudo (sem implementação PSP) |
| NFS-e integração | `Exeq_Hub_NFSe_Emission_Architecture_Reference.md` | **1.1.0** (addendum emissor próprio; Focus histórico) |
| ADR emissor próprio Nacional | `ADR_NFSE_001_Emissor_Proprio_Nacional.md` | **Aprovado** (PO 2026-07-29 — SEFIN/ADN + DANFSe) |
| ADR emissor próprio NF-e SEFAZ | `ADR_NFE_001_Emissor_Proprio_SEFAZ.md` | **Aprovado + GO desenvolvimento** (PO 2026-08-05 — SP; stub até IE/SEFAZ) |
| Plano desenvolvimento emissor próprio | `Exeq_Hub_Plano_Desenvolvimento_Emissor_Proprio_NFSe.md` | **Autorizado PO** (início 2026-07-29 — visão gestão) |
| DoD segurança NFS-e/SEFIN | `Exeq_Hub_DoD_Seguranca_NFSe_SEFIN.md` | G-SEC P0 aprovado; P1 (pentest escopo pronto) |
| Briefing pentest SEC-P1-09 | `Exeq_Hub_NFSe_Pentest_Briefing_SEC_P1_09.md` | Escopo |
| Relatório pentest GL-01 | `Exeq_Hub_NFSe_Pentest_Report_SEC_P1_09.md` | Interno formal 2026-07-30 |
| Onboarding multi-CNPJ | `Exeq_Hub_NFSe_Onboarding_Multi_CNPJ.md` | `nfse_onboard_tenant` |
| Ops convênio HTTP ADN | `Exeq_Hub_NFSe_Ops_Convenio_HTTP.md` | `nfse_smoke_convenio_http` |
| ARD canal WhatsApp + mensageria | `Exeq_Hub_ARD_WhatsApp_NFSe_Mensageria.md` | **0.2.0** — gate Fase 3; item 17 decidido (gateway dual Evolution + Meta) |
| UX análise nav + responsive | `Exeq_Hub_UX_Analise_Navegacao_Responsive.md` | **0.1.0** — UI foundations; protótipo `frontend/prototypes/ux-foundations-nav-responsive.html` |
| QA roteiro emissão via WhatsApp | `Exeq_Hub_QA_Roteiro_WhatsApp_NFSe.md` | **0.5.0** — Fases 1–3 + smoke nativo Ricardo + WA-IA stub |
| LLR emissor próprio | `Exeq_Hub_LLR_Emissor_Proprio_NFSe_Nacional.md` | **0.3.0** (RF/EX + NT 008 v1.02) |
| LLR UI NF-e B2B (sem estoque) | `Exeq_Hub_LLR_NFe_UI_B2B_Sem_Estoque.md` | **0.2.0** — reanálise greenfield + reuso NFS-e; allowed_actions; G-IMPACT |
| LLR domínio NF-e SEFAZ greenfield | `Exeq_Hub_LLR_NFe_Dominio_SEFAZ_Greenfield.md` | **0.1.0** — FSM, número, snapshot, tax, EX-*, API, gates G-EMIT-NFE |
| Reanálise impacto NF-e × NFS-e homologada | `Exeq_Hub_NFe_Reanalise_Impacto_NFSe_Homologada.md` | **1.0.0** — inventário reuso, riscos recalibrados, parecer Aprovado c/ ressalvas |
| Tickets U3 NF-e I1–I8 | `Exeq_Hub_NFe_U3_Tickets_I1_I8.md` | Backlog G-SPIKE → G-EMIT-NFE |
| Multi-UF NF-e U4 | `Exeq_Hub_NFe_U4_Multi_UF.md` | Catálogo 10 UFs + matriz QA (G-MULTI-10) |
| U5 interestadual + CCe backlog + G-EMIT SP | `Exeq_Hub_NFe_U5_Interestadual_CCe_G_EMIT.md` | RF-23/CFOP · CCe via U14 · runbook homolog |
| U14 CCe 110110 | `Exeq_Hub_NFe_U14_CCe.md` | API + artefato + UI (stub/HTTP dry-run) |
| U15 Inutilização nNF | `Exeq_Hub_NFe_U15_Inutilizacao.md` | InutNFe + counter + `POST …/config/inutilize` |
| U16 UI inut + RF-71 e-mail | `Exeq_Hub_NFe_U16_UI_Inut_RF71_Email.md` | Hub inutilizar · e-mail XML/DANFE outbox |
| U17 ops RF-64/92/91 | `Exeq_Hub_NFe_U17_Ops_RF64_RF92_RF91.md` | DANFE retry beat · poll_exhausted · metrics API |
| U18 reconcile + preflight | `Exeq_Hub_NFe_U18_Reconcile_Preflight.md` | RF-46 órfãs · RF-41 lite sem POST |
| U19 hardening + freeze | `Exeq_Hub_NFe_U19_Hardening_Freeze.md` | Outbox 1× · denegada · cancel órfão · freeze código |
| U20–U22 sprint pré-G-EMIT | `Exeq_Hub_NFe_U20_U22_Sprint.md` | RF-44 attempts · gate · catalog · Hub KPIs |
| U23 G-EMIT prep | `Exeq_Hub_NFe_U23_G_EMIT_Prep.md` | OpenAPI attempts · checklist CLI · CCe/inut log |
| U24 ops lista + retry PDF | `Exeq_Hub_NFe_U24_Ops_List_Retry_PDF.md` | filtros pdf_pending/denegada · POST retry-pdf |
| Manual de telas (PO) | `Exeq_Hub_Manual_Telas_PO.md` + `.html` | Uso do Hub `/app/` · mocks · fluxos · checklist demo |
| Hub V4 UX Ledger | `Exeq_Hub_V4_UX_QA.md` | Shell `/hub/` · Unfold · wizard NFS-e · DoD QA |
| U6 config/gate/discard/clone | `Exeq_Hub_NFe_U6_Config_Gate.md` | T0/T6 API + FSM operator paths (stub) |
| U7 outbox NF-e RF-70 | `Exeq_Hub_NFe_U7_Outbox.md` | `nfe.authorized` / rejected / cancelled |
| U8 lista + timeline | `Exeq_Hub_NFe_U8_Lista_Timeline.md` | Filtros T1 + `GET …/events` |
| U9 NumberSeries + G-EMIT ops | `Exeq_Hub_NFe_U9_NumberSeries_G_EMIT.md` | DoD #4 concorrência · checklist G-EMIT |
| U10–U12 fábrica (OpenAPI · imutab. · UI) | `Exeq_Hub_NFe_U10_U12_Factory.md` | DoD #9 OpenAPI + freeze snapshot + polish stub |
| U13 EX-SEC NF-e + throttle | `Exeq_Hub_NFe_U13_EX_SEC.md` | Isolamento multi-tenant + `nfe_write` rate limit |
| RF-72 mídia WhatsApp NF-e | `Exeq_Hub_NFe_RF72_Midia_WhatsApp.md` | DANFE/XML se sessão canal ligar `nfe.authorized` |
| Reforma Tributária / RTC | `Exeq_Hub_Reforma_Tributaria_RTC_MultiDocumento_Estudo_Tecnico.md` | **0.1.0-draft** (estudo direção — IBS/CBS/IS, multi-DF-e, contábil) |
| ADR RTC execução | `ADR_RTC_001_Priorizacao_Pilares.md` | **Aceito** (PO 2026-07-26 — pilares 1→5→2→4→3) |
| ADR Matriz ISS N0/N1/N2 | `ADR_FISCAL_001_Matriz_ISS_N0_N1_N2.md` | **Aprovado + GO** (PO 2026-08-11 — readiness + templates) |
| Billing Inter | `Exeq_Hub_Inter_Billing_Integration_Study.md` | **1.0.0** (Sprint 5 — Inter first / BolePix v3) |
| v4 API | `Exeq_Hub_v4_API_OpenAPI.md` + `openapi-v4.yaml` | **4.1.0-draft** (DAS + billing + proxies) |
| v5 UX | — | Pendente |

Stubs Word `Exeq_Hub_v1.docx` / `Exeq_Hub_v2.docx` **não** são mais autoridade — usar os `.md` acima.

O doc NFS-e prevalece só em **estratégia de emissão/provider/layout**; schema continua v3.1 e domínio v1.
