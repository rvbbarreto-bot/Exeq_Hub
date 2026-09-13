# ADR-NFE-ENTRADA-001 — Captura Fiscal NF-e de Entrada (Distribuição DFe + Manifestação)

| Campo | Valor |
|-------|--------|
| Status | **Proposta (Fase 2)** — aguarda implementação Fase 3 |
| Data | 2026-09-07 |
| Decisores | PO, Tech Lead, Engenharia Fiscal |
| Relacionado | `ADR_NFE_001` (saída), NT 2014.002, MOC NF-e 4.00 |
| Escopo MVP | Distribuição DFe (`distNSU`), persistência NSU, NF-e recebidas, manifestação destinatário (4 eventos), Hub V4 lista/detalhe |
| Fora MVP | DANFE entrada, escrituração/estoque, consNSU manual, consChNFe, S3/MinIO, A3 |

---

## 1. Contexto

O EXEQ Hub emite NF-e de **saída** (modelo 55) via SEFAZ por UF. Não existe hoje integração com o **Ambiente Nacional** para:

- `NFeDistribuicaoDFe` (consulta documentos destinados ao CNPJ)
- Manifestação do Destinatário (eventos 2102xx)

A ADR-NFE-001 explicitamente excluiu entrada/compra e manifesto DFe do MVP de emissão. Este ADR cobre um **módulo complementar**, reutilizando certificado A1, storage, Celery e multi-tenant existentes.

---

## 2. Decisão

Implementar **Captura Fiscal — NF-e de Entrada** como extensão do app `apps/nfe`, com integração isolada em `integrations/sefaz_nfe/distribuicao/` e `integrations/sefaz_nfe/manifestacao/`.

### 2.1 Princípios

| ID | Decisão |
|----|---------|
| E-01 | **Não** reutilizar `NfeInvoice` para documentos de entrada — entidade separada `NfeEntradaDocument` |
| E-02 | NSU persistido em PostgreSQL (`NfeDistribuicaoCursor`); Redis apenas para lock opcional |
| E-03 | Endpoint AN centralizado (≠ endpoints UF de emissão) |
| E-04 | Certificado A1 existente (`DigitalCertificate`); `key_usage` inclui `"nfe"` |
| E-05 | **Confirmação da Operação (210200) nunca automática** — ação explícita do usuário |
| E-06 | `resNFe` ≠ XML completo; status `xml_pending` até `procNFe` |
| E-07 | Idempotência: `UNIQUE(tenant, access_key)` + `UNIQUE(tenant, provider, nsu)` |
| E-08 | cStat **137** = sucesso sem documentos; cStat **656** = bloqueio temporário |
| E-09 | Camadas: View → Serializer → App Service → Integration → ORM |
| E-10 | Feature flag: `NFE_ENTRADA_ENABLED` + `tenant.settings.nfe_entrada_enabled` |

---

## 3. Modelagem (DER)

```
Tenant ──┬── Provider ──┬── NfeDistribuicaoCursor (1:1 por provider)
         │              └── NfeEntradaDocument (1:N)
         │                      └── NfeEntradaManifestation (1:N)
         └── DigitalCertificate (reuso)

NfeEntradaDocument ── FK ── StoredFile (XML)
NfeEntradaManifestation ── FK ── StoredFile (XML evento, opcional)
NfeDistribuicaoSyncLog (auditoria por consulta)
```

### 3.1 NfeDistribuicaoCursor

| Campo | Tipo | Notas |
|-------|------|-------|
| tenant | FK | TenantOwnedModel |
| provider | FK OneToOne | Provider |
| cnpj | CharField(14) | denormalizado |
| ult_nsu | CharField(15) | default "0" |
| max_nsu | CharField(15) | último maxNSU retornado |
| last_query_at | DateTimeField | |
| last_c_stat | CharField(3) | |
| last_x_motivo | TextField | |
| blocked_until | DateTimeField | null; preenchido em 656 |
| automatic_enabled | BooleanField | default False |
| interval_seconds | PositiveIntegerField | default 3600 |
| tp_amb | CharField(1) | 1 prod / 2 homolog |

### 3.2 NfeEntradaDocument

| Campo | Tipo | Notas |
|-------|------|-------|
| tenant, provider | FK | |
| nsu | CharField(15) | NSU do lote AN |
| schema_type | CharField | resNFe, procNFe, resEvento, procEventoNFe |
| access_key | CharField(44) | nullable para eventos sem chave |
| issuer_cnpj, issuer_name | | emitente |
| recipient_cnpj | CharField(14) | |
| number, series | | extraídos do resumo |
| issue_date | DateField | |
| total_cents | BigIntegerField | |
| nfe_status | CharField | situação NF-e se conhecida |
| xml_status | CharField | pending, available, error |
| manifest_status | CharField | none, ciencia, confirmada, desconhecida, nao_realizada |
| xml_hash | CharField(64) | SHA-256 |
| stored_file | FK StoredFile | null se só resumo |
| raw_metadata | JSONField | campos extras do parser |

**Constraints:** `UNIQUE(tenant_id, access_key)` where access_key not null; `UNIQUE(tenant_id, provider_id, nsu)`

### 3.3 NfeEntradaManifestation

| Campo | Tipo | Notas |
|-------|------|-------|
| document | FK | NfeEntradaDocument |
| tp_evento | CharField(6) | 210210, 210200, 210220, 210240 |
| n_seq | PositiveSmallIntegerField | |
| protocol | CharField | nProt retorno |
| c_stat, x_motivo | | retorno SEFAZ |
| status | CharField | pending, accepted, rejected |
| actor_user | FK User | null para worker |
| actor_ip | GenericIPAddressField | null |
| stored_file | FK | XML evento assinado |
| correlation_id | UUID | |

---

## 4. Integração

### 4.1 Ambiente Nacional — NFeDistribuicaoDFe

| Ambiente | URL (referência oficial) |
|----------|--------------------------|
| Homolog | `https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx` |
| Produção | `https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx` |

Operação MVP: **distNSU** (`ultNSU`).

### 4.2 Manifestação — NFeRecepcaoEvento4

Reutiliza `post_nfe_evento()` + `sign_evento_nfe_xml()` com builders novos em `manifestacao/evento.py`.

| tpEvento | Descrição | Auto? |
|----------|-----------|-------|
| 210210 | Ciência da Emissão | Manual |
| 210200 | Confirmação da Operação | Manual + confirmação UI |
| 210220 | Desconhecimento | Manual + confirmação UI |
| 210240 | Operação não Realizada | Manual + xJust obrigatória |

Endpoint evento: `SefazNfeEndpoints.recepcao_evento` por UF da chave (primeiros 2 dígitos IBGE).

---

## 5. Workers

| Task | Trigger | Descrição |
|------|---------|-----------|
| `nfe.distribuicao_sync` | POST API/Hub ou beat | Uma rodada distNSU para (tenant, provider) |
| `nfe.distribuicao_tick` | Celery Beat | Enfileira CNPJs com `automatic_enabled` |

Lock: `select_for_update()` em `NfeDistribuicaoCursor` (MVP); Redis `lock:nfe-distrib:{tenant}:{cnpj}` em fase posterior se multi-worker competir.

---

## 6. API (REST `/api/v1/`)

| Método | Path | Ação |
|--------|------|------|
| GET | `nfe/entrada/` | Lista documentos (filtros) |
| GET | `nfe/entrada/<uuid>/` | Detalhe |
| POST | `nfe/entrada/sync/` | Dispara sync manual |
| GET | `nfe/entrada/distribution/status/` | Status cursor NSU |
| PUT | `nfe/entrada/distribution/config/` | automatic_enabled, interval |
| POST | `nfe/entrada/<uuid>/manifest/` | Enviar manifestação |
| GET | `nfe/entrada/<uuid>/xml/` | Download XML |

---

## 7. Hub V4

| Path | Tela |
|------|------|
| `/hub/nfe/entrada/` | Lista + KPIs |
| `/hub/nfe/entrada/<uuid>/` | Detalhe + ações manifestação |
| `/hub/nfe/entrada/config/` | Config distribuição automática |

Sidebar: item **"NF-e de Entrada"** sob Exeq Fiscal, flag `nfe_entrada_enabled_nav`.

---

## 8. Configuração

```env
NFE_ENTRADA_ENABLED=false
NFE_ENTRADA_HTTP_MODE=stub          # stub | http
NFE_ENTRADA_DIST_TIMEOUT=60
NFE_ENTRADA_DIST_MAX_RETRIES=3
NFE_ENTRADA_DIST_BACKOFF_BASE=300   # segundos após 137
NFE_ENTRADA_BLOCK_656_SECONDS=3600
NFE_ENTRADA_DEFAULT_INTERVAL=3600
NFE_ENTRADA_SYNC_BATCH_LIMIT=50     # docZip por rodada
```

---

## 9. Testes obrigatórios

- distNSU: 137, 656, lote múltiplo, NSU persistido, duplicata
- Certificado: válido, expirado, CNPJ divergente
- XML: resNFe vs procNFe, hash, storage
- Manifestação: 4 tipos, rejeição, idempotência
- Multi-tenant: isolamento tenant A/B

---

## 10. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Consumo indevido (656) | blocked_until + intervalo conservador |
| NSU fora de ordem | transação + lock cursor |
| Confirmação automática | gate explícito na UI e service |
| Histórico AN limitado | messaging honesto na UI |
| Cert sem purpose nfe | migration dados + upload default |

---

## 11. Ordem de implementação (Fase 3)

1. Migrations + models
2. Stub provider + parse docZip
3. NfeDistribuicaoService + testes
4. Http provider (homolog)
5. Celery tasks + beat
6. Manifestação (ciência primeiro)
7. API REST
8. Hub V4 UI
9. Homologação manual AN

---

## 12. Referências normativas

- NT 2014.002 — Distribuição de DF-e
- Manual de Orientação do Contribuinte NF-e 4.00
- Schemas: `distDFeInt`, `retDistDFeInt`, `resNFe`, `procNFe`, `envEvento`
- WSDL NFeDistribuicaoDFe (Ambiente Nacional)
