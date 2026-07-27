# ADR-RTC-001 — Programa Reforma Tributária (pilares 1→5→2→4→3)

| Campo | Valor |
|-------|-------|
| Status | **Aceito** (autorização PO 2026-07-26) |
| Tipo | ADR de execução + mitigação de risco |
| Escopo | NFS-e Nacional (Focus `nfsen`) — **não** NF-e produto nesta onda |
| Prioridade PO | Pilar **1 → 5 → 2 → 4 → 3** |

## Contexto

Gestão autorizou a fábrica a executar a priorização do Adendo Técnico A da RFC-001.
O Hub hoje emite NFS-e com payload **ISS-only**. A Reforma exige grupos IBS/CBS,
classificação CST/cClassTrib, catálogo oficial e snapshot forense.

## Decisão

1. Entregar os cinco pilares em onda única controlada, **sem** quebrar emissão ISS.
2. Introduzir bounded context lean em `apps/fiscal` (`rtc_*`) + wiring em issuance/mappers.
3. Amend documental mínimo ao DER (tabelas RTC globais, não tenant-owned de regra municipal).
4. **Não** abrir NF-e/NFC-e nesta ADR.

## Mitigações de risco (tech lead)

| Risco | Mitigação |
|-------|-----------|
| Focus rejeita campos RTC desconhecidos / ADN ainda não exige | `RTC_NFSEN_MODE=off\|shadow\|emit` (default **`shadow`**: calcula + grava snapshot, **não** envia ao Focus até validação) |
| Parada abrupta quando ADN exigir | Trocar para `emit` por env/tenant após golden-file Focus; Pilar 1 já prepara payload |
| Passivo silencioso (código errado) | Pilar 5: se lista nacional publicada, **exige** `codigo_tributacao_nacional_iss` ∈ lista |
| CST inventado | Pilar 2: códigos só de `RtcClassificationCode` na versão normativa publicada |
| Defesa fiscal fraca | Pilar 4: snapshot consolidado (`forensic`) com regra ISS + RTC + catálogo + hash |
| NT sem dono | Pilar 3: `RtcNormativeVersion` com `nt_refs`, changelog, owner, published/superseded |
| Fórmulas 2026 vs 2027 | `formula_period` no assessment; teste unitário por faixa de competência |
| Escopo ERP | Continua TaxEngine próprio; Focus só transporta; Hub **não** vira apuração contábil completa |

## Ordem de entrega nesta fábrica

1. Modelos + seed normativo mínimo (CST `000`, cClassTrib seed, IndOp seed) — base 5/2/3  
2. Assessment IBS/CBS 2026 + guard catálogo — pilares 1/5  
3. Wiring create_nf_issue + mapper condicional — pilar 1  
4. Forensic snapshot — pilar 4  
5. Admin/governança NT — pilar 3  
6. Testes unitários obrigatórios  

## Consequências

- Novas tabelas: `rtc_normative_versions`, `rtc_classification_codes` (amend v3.1).
- `FiscalRuleSnapshot.snapshot` passa a incluir chave `forensic` (compatível; leitores antigos ignoram).
- Feature flags em settings; produção permanece segura em `shadow` até go-live ADN/Focus.

## Fora de escopo (explícito)

NF-e, NFC-e, split payment bancário, portal contador, locação H2/H3, Imposto Seletivo completo.
