# NF-e de Entrada — Distribuição DFe e Manifestação (EXEQ Hub)

Documento operacional e roteiro de homologação para o módulo **Captura Fiscal — NF-e de Entrada** (ADR-NFE-ENTRADA-001).

| Versão | Data | Escopo |
|--------|------|--------|
| 1.0 | 2026-09-07 | distNSU, manifestação 2102xx, Hub V4, API REST |

---

## 1. Visão geral

O módulo consulta o **Ambiente Nacional** (`NFeDistribuicaoDFe`) para capturar documentos destinados ao CNPJ do tenant e permite **Manifestação do Destinatário** (eventos 210210–210240).

**Não faz parte do MVP:** DANFE de entrada, escrituração, estoque, `consNSU`/`consChNFe` manual, certificado A3.

---

## 2. Pré-requisitos

### 2.1 Feature flags

```env
NFE_ENTRADA_ENABLED=true
NFE_ENTRADA_HTTP_MODE=stub    # lab: stub | homolog: http
NFE_ENTRADA_STUB_MODE=138     # stub: 138 | 137 | 656
NFE_ENTRADA_DIST_TIMEOUT=60
NFE_ENTRADA_BLOCK_656_SECONDS=3600
NFE_ENTRADA_DEFAULT_INTERVAL=3600
NFE_ENTRADA_SYNC_BATCH_LIMIT=50
NFE_ENTRADA_TICK_INTERVAL_SECONDS=300
NFE_ENTRADA_TICK_BATCH_LIMIT=50
```

No tenant (Admin ou seed):

```json
{ "nfe_entrada_enabled": true }
```

### 2.2 Certificado digital

- A1 válido em `DigitalCertificate` com `key_usage` incluindo **`nfe`**
- CNPJ do certificado = CNPJ destinatário (`Provider.document`)
- Ambiente do cursor (`tp_amb`): `2` homolog / `1` produção

### 2.3 Celery (consulta automática)

- Worker Celery ativo
- Beat com task `nfe-entrada-distribuicao-tick` → `nfe.distribuicao_tick`
- Cursor com `automatic_enabled=true` e `interval_seconds` ≥ 300

---

## 3. Ambiente Nacional (HTTP)

| Ambiente | URL |
|----------|-----|
| Homologação | `https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx` |
| Produção | `https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx` |

Para homologação real:

```env
NFE_ENTRADA_HTTP_MODE=http
NFE_ENTRADA_HTTP_DRY_RUN=false
```

Manifestação usa `NFeRecepcaoEvento4` por **UF da chave** (reutiliza `post_nfe_evento`).

---

## 4. Fluxos operacionais

### 4.1 Consulta manual (distNSU)

**Hub:** `/hub/nfe/entrada/` → **Consultar AN**

**API:**

```http
POST /api/v1/nfe/entrada/sync/
Authorization: Bearer …
Content-Type: application/json

{ "provider_id": "<uuid-provider>" }
```

Resposta `202` com `task_id`. Com `CELERY_TASK_ALWAYS_EAGER=true` (lab) executa inline.

### 4.2 Interpretação de cStat

| cStat | Significado | Ação EXEQ |
|-------|-------------|-----------|
| **137** | Nenhum documento localizado | Normal; aguardar intervalo |
| **138** | Documentos localizados | Processar lote; avançar `ultNSU` |
| **656** | Consumo indevido | `blocked_until` + backoff; **não** insistir |

### 4.3 resNFe vs procNFe

- **resNFe:** resumo; `xml_status=pending` até receber **procNFe**
- **procNFe:** XML completo; storage local + `xml_status=available`
- Após **Ciência (210210)** o sistema enfileira nova consulta para tentar obter o XML completo

### 4.4 Manifestação

| tpEvento | Descrição | Confirmação UI |
|----------|-----------|----------------|
| 210210 | Ciência da Emissão | Não |
| 210200 | Confirmação da Operação | **Obrigatória** (`confirmed=true`) |
| 210220 | Desconhecimento | **Obrigatória** |
| 210240 | Operação não Realizada | **Obrigatória** + justificativa ≥ 15 chars |

**Regra de produto (E-05):** confirmação da operação **nunca** é automática.

---

## 5. Hub V4 — telas

| Rota | Conteúdo |
|------|----------|
| `/hub/nfe/entrada/` | KPIs, cursor NSU, filtros, tabela |
| `/hub/nfe/entrada/<uuid>/` | Detalhe, manifestação, histórico |
| `/hub/nfe/entrada/config/` | Consulta automática + intervalo |

Sidebar: **NF-e de Entrada** (flag `nfe_entrada_enabled_nav`).

---

## 6. API REST (resumo)

Ver `Docs/openapi-nfe-entrada-v1.yaml` e `GET /api/v1/openapi.json`.

---

## 7. Homologação manual AN

Checklist detalhado: [`nfe-entrada-homologacao-an.md`](./nfe-entrada-homologacao-an.md).

Ordem sugerida:

1. Certificado A1 homolog + CNPJ destinatário cadastrado
2. `NFE_ENTRADA_HTTP_MODE=http`, `tp_amb=2`
3. Primeira consulta distNSU — validar cursor (`ultNSU`, `maxNSU`, cStat)
4. Documento resNFe na lista — XML pendente
5. Ciência 210210 — protocolo aceito
6. Nova consulta — procNFe se AN disponibilizar
7. Download XML
8. Confirmação 210200 com checkbox/confirmação explícita
9. Simular 656 (consultas abusivas) — validar bloqueio
10. Multi-CNPJ: isolamento tenant A/B

Registrar evidências: `NfeDistribuicaoSyncLog`, XML armazenado, `NfeEntradaManifestation.protocol`.

---

## 8. Testes automatizados

### 8.1 Suíte NF-e entrada

```powershell
cd Exeq_Hub
python -m pytest `
  apps/nfe/tests/test_entrada_*.py `
  apps/hub_v4/tests/test_nfe_entrada_hub*.py `
  integrations/sefaz_nfe/tests/test_distribuicao_*.py `
  integrations/sefaz_nfe/tests/test_manifestacao_*.py `
  -q
```

### 8.2 Cobertura mínima 80% (`apps.nfe.entrada`)

```powershell
.\scripts\test_nfe_entrada_coverage.ps1
```

Ou:

```powershell
python -m pytest apps/nfe/tests/test_entrada_*.py apps/hub_v4/tests/test_nfe_entrada_hub*.py `
  --cov=apps.nfe.entrada --cov-report=term-missing --cov-fail-under=80 -q
```

### 8.3 Camadas de teste

| Camada | Arquivos | Foco |
|--------|----------|------|
| Unitário | `test_entrada_listing`, `_artifacts`, `_serializers`, `_document_service`, `_cursor`, `_feature` | Filtros, storage, serializers, upsert |
| Integração | `test_entrada_integration` | sync → API → manifest |
| Sistema | `test_entrada_system` | API + Hub + Celery tick |
| UI Hub | `test_nfe_entrada_hub_ui` | Campos, filtros, botões, KPIs |

---

## 9. Troubleshooting

| Sintoma | Causa provável | Verificar |
|---------|----------------|-----------|
| 403 API/redirect Hub | Flag desligada | `NFE_ENTRADA_ENABLED`, `tenant.settings` |
| 656 repetido | Consumo indevido | `blocked_until`, intervalo |
| XML sempre pendente | Só resNFe no AN | Ciência + nova consulta |
| Manifestação rejeitada | Certificado/CNPJ | `DigitalCertificate`, UF da chave |
| Sync não automático | Beat/cursor | `automatic_enabled`, Celery Beat |

---

## 10. Referências

- ADR-NFE-ENTRADA-001
- NT 2014.002 — Distribuição DF-e
- MOC NF-e 4.00
- OpenAPI: `Docs/openapi-nfe-entrada-v1.yaml`
