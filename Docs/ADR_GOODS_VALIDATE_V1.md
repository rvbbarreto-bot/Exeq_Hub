# ADR-GOODS-VALIDATE-V1 — Validação cruzada e serialização mercadorias (NF-e 55 / NFC-e 65)

| Campo | Valor |
|-------|--------|
| Status | **Aprovado pelo PO** — baseline v1 ALE |
| Data | 2026-09-07 |
| Autores | Tech Lead + Engenharia fiscal EXEQ Hub |
| Relaciona | `Exeq_Hub_Estudo_Tecnico_RTC_NFe_NFCe_Fidelidade_Fiscal.md` v1.0.0 · `ADR_NFE_001` · LLR NF-e / NFC-e kickoff |
| Escopo | Catálogo `NfeProduct`, emissão NF-e/NFC-e, serialização XML `prod` |

---

## 1. Decisões PO (assinatura)

| ID | Decisão |
|----|---------|
| **P1** | **Sem ST na v1 ALE** — perfil `simple_retail` only (5102/102/07) |
| **P2** | **GTIN opcional** — default `"SEM GTIN"` na serialização XML |
| **P3** | **warn no cadastro**, **block no emit HTTP produção** |
| **P4** | **Um flag** `GOODS_CROSS_VALIDATE` (`off` \| `warn` \| `block`) para NF-e e NFC-e |
| **P5** | **Amend DER** antes de migration prod — `gtin` nesta entrega; campos ST retido na fase ST |

**Assinatura PO:** _________________________ Data: ___/___/2026

---

## 2. Contexto

Multi-tenant fiscal exige **um motor de validação**, **snapshot imutável** e **emissão rigorosa**. O emissor Sebrae expõe dezenas de tags XML; o Hub abstrai via catálogo enxuto + motor + serializador.

Estado anterior: `NFE_CROSS_VALIDATE` só NF-e; NFC-e sem L5–L8; GTIN hardcoded; ST sem gate de perfil.

---

## 3. Decisões técnicas

| Tema | Decisão |
|------|---------|
| Flag | `GOODS_CROSS_VALIDATE` canônico; `NFE_CROSS_VALIDATE` legado (fallback) |
| Modo efetivo | `catalog` → warn; `emit` + HTTP → block; CI → block |
| Perfil tenant | `tenant.settings.fiscal_profile` default `simple_retail` |
| ST v1 | Bloqueado em `simple_retail` (CFOP 5403/5405/6403/6405, CSOSN 500) |
| GTIN | `NfeProduct.gtin` nullable; `resolve_c_ean(gtin)` → XML |
| Motor | `apps/nfe/cross_validate.py` compartilhado NF-e + NFC-e |
| XML | `integrations/sefaz_nfe/prod_fields.py` — `cEAN` / `cEANTrib` |
| DER | Amend v3.1 § `NfeProduct.gtin` antes de migration prod |

---

## 4. Defaults por ambiente

| Ambiente | `GOODS_CROSS_VALIDATE` | `NFE_CATALOG_STRICT` | Perfil ALE |
|----------|------------------------|----------------------|------------|
| Lab stub | `warn` | false | `simple_retail` |
| Homolog HTTP | `warn` | true | `simple_retail` |
| **Produção** | **`block`** | **true** | **`simple_retail`** |

---

## 5. Fora do escopo v1

- Grupo XML `ICMSSN500` completo (fase ST)
- `<CEST>` condicional ST (fase ST)
- Validação GS1 módulo 10 (fase GTIN+)
- Override fiscal RF-26 com forensic

---

## 6. Gate fase ST (futuro)

Abrir perfil `retail_st` quando: checklist ST-0 + golden CSOSN500 + homolog SP + PO.

---

## 7. DoD engenharia

- [x] `GOODS_CROSS_VALIDATE` em settings
- [x] NFC-e usa `cross_validate_invoice_item`
- [x] `simple_retail` bloqueia ST no catálogo e emit
- [x] Migration `gtin` + Hub form
- [x] XML usa GTIN ou `SEM GTIN`
- [x] Testes `apps/fiscal/tests/test_goods_validate_v1.py`

---

## 8. Changelog

| Versão | Data | Notas |
|--------|------|-------|
| 1.0.0 | 2026-09-07 | Decisões P1–P5 PO; implementação v1 (flag, perfil, gtin, NFC-e cross-validate) |
