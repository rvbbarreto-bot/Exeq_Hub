# Hub V4 — Biblioteca de componentes UI (fiscal v1)

Stack: templates Django em `apps/hub_v4/templates/hub_v4/`, CSS `apps/hub_v4/static/hub_v4/css/exeq-ledger.css`, tags `apps/hub_v4/templatetags/hub_v4_tags.py`.

> Nota: o briefing original citava Django Unfold; o Hub fiscal roda no shell **Hub V4** custom. Componentes abaixo são reutilizáveis em DAS, Boleto, Food etc.

## Tokens (Parte 2 do design)

| Token | CSS var | Uso |
|-------|---------|-----|
| ink-900 | `--ink-900` | Sidebar, texto principal |
| surface | `--surface` | Fundo da página |
| card | `--card` | Cards e formulários |
| border | `--border` | Bordas 1px |
| accent | `--accent` (#0F6B5C) | Primário |
| accent-hover | `--accent-hover` | Hover botão primário |
| success / danger / warning / neutral | `--*-bg` + cor texto | Status |

Tipografia: `--font-display` (títulos), `font-variant-numeric: tabular-nums` em `.num` e KPIs.

## Componentes

### `{% status_badge status %}`
Pill com ponto colorido + label. Mapeia status de documentos (NF-e, NFC-e, NFS-e, cobranças).

```django
{% load hub_v4_tags %}
{% status_badge inv.status %}
```

Arquivo: `components/status_badge.html` · tones: `success`, `danger`, `warning`, `neutral`.

### `{% import_status_badge status %}`
Variante para linhas da importação Excel (NOVO, ATUALIZAÇÃO, ERRO…).

### `{% empty_state title description cta_label cta_url %}`
Estado vazio com CTA opcional.

```django
{% url 'hub-v4-nfe-emit' as emit_url %}
{% empty_state "Nenhuma NF-e ainda" "Emita a primeira nota." "Emitir NF-e →" emit_url %}
```

### `{% kpi_card label value hint %}`
Card de métrica para banners de importação e dashboards.

```django
<div class="metric-grid">
  {% kpi_card "Processadas" preview.summary.total %}
</div>
```

### Banner de resumo
Classes utilitárias: `.banner`, `.banner-success`, `.banner-warning`.

### Upload dropzone
`.upload-dropzone` + JS drag/drop (ver `nfe/product_import.html`).

### Rodapé sticky de formulário
`.form-sticky-footer` — Cancelar/Voltar à esquerda, primário à direita (`margin-left: auto`).

### Tabela responsiva
- Desktop: `.table-wrap.desktop-only` + `table.data` (thead sticky via CSS global).
- Mobile: `.mobile-cards` + `.mobile-data-card` por registro.

### Tooltip de ajuda
`<abbr class="field-tip" title="…">ⓘ</abbr>` — contexto técnico sem bloco fixo.

### Feedback (toast-like)
Mensagens Django em `base.html` → `<ul class="messages">` estilizado como toast (entrada suave). Auto-dismiss pode ser adicionado em `hub-v4.js` v2.

## Telas fiscal modernizadas (Parte 1)

| Rota | Template |
|------|----------|
| `/hub/nfe/` | `nfe/list.html` |
| `/hub/nfe/emitir/` | `nfe/form.html` |
| `/hub/nfce/` | `nfce/list.html` |
| `/hub/nfce/pdv/` | `nfce/pdv.html` |
| `/hub/nfe/produtos/` | `nfe/products_list.html` |
| `/hub/nfe/produtos/novo/` | `nfe/product_form.html` |
| `/hub/nfse/` | `nfse/list.html` |
| `/hub/nfse/emitir/` | `nfse/wizard.html` |
| `/hub/nfse/<id>/` | `nfse/detail.html` |
| `/hub/nfse/<id>/documentos/` | `nfse/documents.html` |
| import | `nfe/product_import*.html` |

### Layout de detalhe
Classes: `.detail-header`, `.detail-grid`, `.detail-field`, `.detail-text` — usado em NFS-e detail.

## Backlog v2 (não implementado)

- Skeleton/spinner global em emissão SEFAZ
- Toast auto-dismiss + fila
- Sticky footer em formulários restantes (serviços, clientes)
- Protótipo Figma separado (HTML serve como referência navegável local)
