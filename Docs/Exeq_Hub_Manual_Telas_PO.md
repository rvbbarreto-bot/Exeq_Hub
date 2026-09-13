# EXEQ Hub — Manual de Telas (PO)

| Campo | Valor |
|-------|--------|
| Público | Product Owner, CS, onboarding, treino comercial |
| App | `http://localhost:8000/app/` |
| Versão | 1.0 · 2026-08-08 |
| Documento visual | **[Exeq_Hub_Manual_Telas_PO.html](./Exeq_Hub_Manual_Telas_PO.html)** (abrir no navegador · mocks + fluxos + checklist 15 min) |

---

## Uso

1. Abra o HTML no Chrome/Edge (duplo clique ou arraste o arquivo).
2. Para PDF: **Ctrl+P** → Salvar como PDF.
3. Ambiente ao vivo para demo real: subir Hub e abrir `/app/`.

O HTML contém **mockups fiéis** de cada tela (sidebar, KPIs, listas, CTAs), fluxos passo a passo e checklist de demonstração. Não depende de servidor.

---

## Mapa rápido do menu

| Grupo | Tela | Fluxo principal |
|-------|------|-----------------|
| Cadastros | Prestadores | Novo → CNPJ lookup → salvar |
| Cadastros | Tomadores | Novo → CNPJ/CPF → endereço → salvar |
| Operação | Painel | Ler KPIs cobrança + NFS-e + certificado |
| Operação | Cobranças | Predefinições → Nova → detalhe PDF/status → cancelar |
| Operação | NFS-e | Emitir → processar → autorizada → PDF/XML → cancelar |
| Operação | NF-e | Gate/série → produto → draft → validar → emitir → artefatos/CCe |
| Operação | DAS | Gerar guia → PDF · ver e-CAC |
| Config | Provedor | Inter/Asaas/C6 + testar conexão |
| Config | Certificados | Upload PFX primary |

---

## Onboarding em 1 frase

**Login → Certificado A1 → Prestador → Tomador → (Provedor) → 1ª NFS-e → (Cobrança).**

---

## Transparência de produto

| Módulo | Status de narração PO |
|--------|------------------------|
| NFS-e + Hub + multi-tenant | Demo principal |
| Cobrança | Demo se gateway configurado / sandbox |
| NF-e | Lab/stub até G-EMIT SEFAZ |
| Agenda | API existe; **sem tela dedicada no Hub** ainda |
| WhatsApp | Canal/backend; não como menu principal do Hub v2 |

---

## Screenshots reais (opcional v1.1)

Pastas sugerida: `Docs/manual_po/screenshots/`

| Arquivo | Tela |
|---------|------|
| `01-login.png` | Overlay login |
| `02-painel.png` | Painel |
| `03-prestadores.png` | Prestadores |
| `04-certificados.png` | Certificados |
| `05-cobrancas.png` | Cobranças |
| `06-nfse.png` | NFS-e |
| `07-nfe.png` | NF-e |
| `08-das.png` | DAS |

Com capturas reais, incluir `<img>` no HTML ou anexar no deck comercial.
