# EXEQ Hub V4 — UX/UI Ledger (Django templates + Unfold admin)

| Campo | Valor |
|-------|--------|
| Status | **impl base 2026-08-09** |
| URL operacional | `/hub/` |
| Admin skin | Django Unfold + paleta Ledger |
| SPA legado | `/app/` (mantido) |
| Domínio fiscal / APIs | **não alterados** |

## Entregue

| Item | Local |
|------|--------|
| Tema único **EXEQ Ledger** | `apps/hub_v4/static/hub_v4/css/exeq-ledger.css` |
| Nav obrigatória | `templates/hub_v4/base.html` |
| Dashboard pendências + CTA Emitir | `dashboard.html` + `services.dashboard_context` |
| NFS-e lista (filtros → tabela → pager; mobile cards) | `nfse/list.html` |
| Wizard 4 etapas + modal confirmação | `nfse/wizard.html` + `hub-v4.js` |
| Detalhe + timeline + documentos técnicos | `nfse/detail.html`, `documents.html` |
| Certificados com barra temporal | `certificates.html` |
| Componentes | `templates/hub_v4/components/*` + `templatetags/hub_v4_tags.py` |
| Breakpoints XL/Desktop/Tablet/Mobile | CSS media queries |
| Unfold admin | `config/settings.py` `UNFOLD` |

## QA checklist (DoD)

### Dashboard
- [ ] Ações pendentes com CTA
- [ ] KPI NFS-e hoje / processando / rejeitadas / certs
- [ ] CTA principal **Emitir NFS-e**

### NFS-e
- [ ] Busca ≤3 cliques (menu NFS-e → busca → detalhe)
- [ ] Wizard com confirmação modal obrigatória
- [ ] Sem gráfico acima da lista

### Mobile
- [ ] Drawer lateral (☰)
- [ ] Lista → cards (sem scroll horizontal da tabela)
- [ ] Targets ≥44px

### A11y
- [ ] `aria-label` no menu/toggle
- [ ] `focus-visible` nos controles
- [ ] Botões nativos (não div clicável)

### Não-regredir
- [ ] API `/api/v1/` intacta
- [ ] `/app/` ainda serve o SPA V3
- [ ] Modelos/issuance services sem mudança de regra

## Como validar

```bash
python -m pip install -r requirements.txt
# subir DB + runserver
# abrir http://127.0.0.1:8000/hub/login/
EXEQ_TEST_SQLITE=1 python -m pytest apps/hub_v4/tests/ -q
```

## Lacunas conscientes (próxima onda UI)

- ~~Download binário PDF/XML na UI~~ **done** (`/hub/nfse/<id>/documentos/<kind>/download/`)
- ~~Wizard 4 etapas + lookup + tributação condicional + revisão viva~~ **done**
- ~~Salvar rascunho no wizard~~ **done** (`save_nf_draft` + `?draft=` + CTA lista/detalhe)
- Lighthouse score medido em CI.
- ~~Port completo de cobrança/DAS emit flows da SPA~~ **done** (Hub `/hub/cobrancas/nova/`, `/hub/das/emitir/`)
- ~~Emit NF-e no Hub~~ **done** (`/hub/nfe/emitir/` — draft+item+emit dominio)
- ~~Cancel/CC-e/download artefatos NF-e na UI Hub~~ **done** (`/hub/nfe/<id>/cancelar|cce|documentos/<kind>/download/`)
- ~~Catálogo de produtos NF-e CRUD no Hub~~ **done** (`/hub/nfe/produtos/`)
- Série/config próximo nº NF-e no Hub (API config já existe).
