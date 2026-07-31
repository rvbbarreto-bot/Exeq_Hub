# ADR-NFSE-001 — Emissor próprio NFS-e Nacional (SEFIN/ADN) + DANFSe EXEQ

| Campo | Valor |
|-------|-------|
| Status | **Aprovado pelo PO** |
| Data | 2026-07-29 |
| Aprovação PO | 2026-07-29 — autoriza spike SEFIN/ADN + fábrica trilhas A∥B (DANFSe) |
| Tipo | ADR de produto + arquitetura de integração |
| Autores | P&O / gestão + Tech Lead (fábrica EXEQ Hub) |
| Relaciona | `Exeq_Hub_LLR_Emissor_Proprio_NFSe_Nacional.md` (LLR v0.3) · `Exeq_Hub_NFSe_Emission_Architecture_Reference.md` (addendum) · `ADR_RTC_001` |
| Código | **Não implementa** nesta ADR — libera spike + fábrica |

---

## 1. Decisão (texto para ata)

**Decidimos que o EXEQ Hub será emissor próprio de NFS-e no Ambiente Nacional (SEFIN/ADN)**, com geração interna do **DANFSe** conforme NT SE/CGNFS-e **008/2026 v1.02**, **sem** depender da API oficial de PDF do governo após **03/08/2026**.

Com esta decisão:

1. O caminho crítico de go-live **não** é Focus nem outro agregador comercial.
2. O código Focus **permanece** no repositório (lab / plano B), mas **não** é default de produção do MVP emissor próprio.
3. Escopo MVP: **somente Ambiente Nacional** (sem municipal legado Betha/GINFES no dia 1).
4. Certificado para emissão automatizada: **somente A1**.
5. Passam a valer o LLR e as trilhas paralelas **A (emissão)** e **B (DANFSe)**.

---

## 2. Contexto

- Gestão definiu eliminar dependência de API de terceiro para emissão (Focus não está em operação).
- Já existem no Hub: TaxEngine, InvoiceEngine, porta `NfseProvider`, certificados, `NfArtifact`, RTC (ADR-RTC-001).
- A referência NFS-e de 2026-07-19 tratava SEFIN como “fase 2 / fora de escopo” — **esta ADR reabre e prioriza SEFIN**.
- NT 008/2026 v1.02 suspende a API `https://adn.nfse.gov.br/danfse/...` em **03/08/2026**; o emissor passa a gerar o DANFSe.

---

## 3. Trade-off consciente (D-09)

| Ganha | Assume |
|-------|--------|
| Independência de agregador / custo por nota | Ciclo de vida do **certificado A1 por tenant** |
| Controle de latência e fila própria | **XMLDSig**, XSD, rejeições SEFIN |
| PDF alinhado à NT sem API gov | Manutenção de **layout DANFSe** a cada NT |
| Alinhamento ao destino “emissor EXEQ” | Monitoramento contínuo de NTs (dono nomeado) |

Agregador comercial (Focus/Spedy) **não** é plano A. Pode existir só como override de lab (LLR RF-51).

---

## 4. Decisões técnicas travadas

| Tema | Decisão |
|------|---------|
| Provider kind MVP | `sefin` (alias doc: `exeq_nacional`) na porta `NfseProvider` |
| Hosts | Homolog: `sefin.producaorestrita.nfse.gov.br` / `adn.producaorestrita.nfse.gov.br`; Prod: `sefin.nfse.gov.br` / `adn.nfse.gov.br` |
| Auth | **Somente mTLS** ICP-Brasil (sem OAuth/API key) |
| Cert | **A1 only** no MVP |
| Emissão | POST tipicamente **síncrono** → `authorized` direto; `polling` = **recuperação** |
| Poll esgotado (EX-POL-02) | Após teto de tentativas → `failed` + alerta ops (não deixar `polling` infinito) |
| XML | Persistido do retorno/consulta autoridade |
| DANFSe | Gerado pelo Hub; campos **somente** do XML da NFS-e; layout NT 008 Anexo I (“DANFSe v2.0”) |
| Corte API gov PDF | **03/08/2026** ([NT 008 v1.02](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/nt-008-se-cgnfse-danfse-20260714-v1-02.pdf)) |
| Município aderente | Cache Hub + refresh da rota oficial de parametrização/convênio |
| `focus_ref` | Reutilizar no MVP como **ref do provedor ativo** (semântica genérica); rename `provider_ref` = backlog DER se necessário |
| RTC | Continua ADR-RTC-001; transporte passa a ser SEFIN no caminho próprio (`RTC_NFSEN_MODE` aplica-se ao mapper DPS) |
| Engine Fiscal monstro | **Não** criar `apps/fiscal_engine`; evoluir módulos existentes |

---

## 5. Condições de release (novas — gates)

Dois gates distintos (não confundir):

| Gate | Critério | Bloqueia |
|------|----------|----------|
| **G-PDF** | Gerador DANFSe NT 008 (autorizada + marca d’água CANCELADA) em lab; layout checklist mínimo aprovado | Dependência de API gov após 03/08 |
| **G-EMIT** | 1 DPS autorizada em homologação SEFIN com mTLS + XML persistido + PDF gerado pelo Hub | Go-live “emissor EXEQ” |

Regras:

- Após **03/08/2026**, **nenhum** ambiente de produção/homologação de produto pode depender de `adn.nfse.gov.br/danfse` para PDF.
- É aceitável chegar a 03/08 com **G-PDF** pronto e **G-EMIT** ainda em spike — desde que não se prometa emissão em produção sem G-EMIT.
- Focus intacto no repo não substitui G-EMIT.

---

## 6. Escopo e fora de escopo

**Dentro (MVP):**  
emissão Nacional, consulta/reconciliação, cancelamento simples, XML + DANFSe (autorizada/cancelada), gate município aderente, A1, testes das EX-* do LLR.

**Fora:**  
municipal legado, substituição (marca SUBSTITUÍDA só quando feature existir), contencioso, manifestações, N vendors, NF-e/NFC-e, pacote contador em lote, A3, Engine Fiscal big bang.

---

## 7. Ordem de execução

1. Estudo oficiais (LLR §1) + download NT 008 v1.02  
2. Spike mTLS (Trilha A) **em paralelo** a protótipo DANFSe (Trilha B)  
3. Adapter + mapper DPS + XMLDSig + FSM (sync-first)  
4. Integração artefatos + QA exceções  
5. Homologação ampliada → produção  

---

## 8. Aprovação

| Papel | Decisão | Data |
|-------|---------|------|
| Produto / PO | **Aprovado** — início imediato das trilhas A∥B | 2026-07-29 |
| Gestão / direção | Ciente do trade-off D-09 (alinhamento prévio) | 2026-07-29 |
| Tech Lead | Executa conforme LLR v0.3 + esta ADR | 2026-07-29 |

**Efeito do “Aprovado”:** liberar spike SEFIN + fábrica das trilhas A/B sem reabrir “Focus first”.

---

## 9. Referências

- LLR: `Docs/Exeq_Hub_LLR_Emissor_Proprio_NFSe_Nacional.md`
- NT 008 v1.02: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/nt-008-se-cgnfse-danfse-20260714-v1-02.pdf  
- Notícia prorrogação: https://www.gov.br/nfse/pt-br/noticias/danfse-novos-ajustes-de-leiaute-e-prorrogacao-do-prazo-para-adequacao  
- Portal docs: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/documentacao-atual  
