# EXEQ Hub — Análise UX: UI foundations, navegação e responsividade

| Campo | Valor |
|-------|-------|
| Tipo | Análise de design (somente; sem implementação em produção) |
| Data | 2026-08-03 |
| Escopo | Shell SPA (`frontend/exeq_hub_layouts_v2_*`) + cadastros Django (`master_data`) |
| Protótipos | `frontend/prototypes/ux-foundations-nav-responsive.html` |

Interpretação do pedido: **bases de UI (UI foundations)** — navegabilidade, hierarquia de tarefas e layout responsivo. Não é código de produto nesta entrega.

---

## 1. Diagnóstico do estado atual

### 1.1 Duas superfícies desconectadas

| Superfície | Onde | Padrão visual | Navegação |
|---|---|---|---|
| Hub operação | `/app/` SPA (JS) | Tema XP / Ledger / Graphite, sidebar 246px | Botões `data-screen` + hash |
| Cadastros | Django templates | Zilla Slab + IBM Plex, paper/teal/gold | Links topbar Prestadores / Tomadores |

**Impacto:** o usuário “sai” do Hub para cadastrar e perde contexto (tenant, breadcrumb, sensação de um produto). Visualmente são **dois produtos**.

### 1.2 Navegação atual (sidebar SPA)

Grupos de fato:

1. **Cadastros** → links externos (Django)
2. **Operação** → Dashboard, Cobranças, NFS-e, DAS  
3. **Config** → Provedor de cobrança, Certificados  

**Problemas de navegabilidade**

- Ordem não segue o fluxo de trabalho fiscal (cadastro → emitir → cobrar → guia).
- Cadastros fora do SPA quebram o modelo mental “tudo em um lugar”.
- Sem busca global, favoritos ou “ações rápidas” no topo.
- Sem indicação de **tarefa primária do dia** (Emitir NFS-e / Cobrar / DAS no vencimento).
- Config misturada perto de operação sem hierarquia “Administração”.

### 1.3 Responsividade

O que já existe (`@media max-width: 980px`):

- Sidebar **some** (`display: none`) — **sem drawer, sem menu hambúrguer, sem bottom bar**.
- KPIs: 4 → 2 colunas.
- Grids e formulários empilham.

**Gap crítico:** em &lt;980px a navegação entre módulos **some**. O hub fica usável só se o usuário lembrar hashes ou recarregar em desktop. Isso bloqueia uso em tablet/campo (prestador no celular).

Cadastros Django têm viewport meta + shell estreito (980px), mas topbar com links que **wrap** sem hierarquia clear em mobile.

### 1.4 Densidade e scan de tabelas

- Listas (NFS-e, cobranças, DAS) em tabela densa — padrão BOM em desktop, **ruim** em mobile sem cards ou scroll horizontal com sticky first column.
- Muitos CTAs de ação em linha (cancelar, PDF, sync) sem progressive disclosure.

### 1.5 Jobs-to-be-done do usuário (prestador / operator)

Ordenados por frequência operacional:

1. Emitir / consultar NFS-e  
2. Cobrança (gerar, ver status pago)  
3. DAS do mês  
4. Cadastro rápido de tomador  
5. Certificado a vencer (alerta, pouco frequente)  
6. Provedor bancário (raro)

A IA e navegação deveriam **elevarem 1–3** e **afastar 5–6** para um grupo “Conta / Configuração”.

---

## 2. Princípios propostos (UI foundations)

1. **Um shell, um sistema de tokens** — unificar SPA + cadastros sob o mesmo cromado (marca, sidebar/top, tipografia).
2. **Navegação = fluxo de negócio**, não lista técnica de endpoints.
3. **Mobile first na navegação**: se a sidebar some, existe **sempre** um substituto (menu off-canvas + bottom nav das 4 ações críticas).
4. **Progressive disclosure**: lista → detalhe (drawer/sheet) em telas estreitas; modal só para ações irreversíveis.
5. **Touch targets ≥ 44px** e legenda sob o ícone na bottom bar.
6. **Estado e feedback** — breadcrumb + título da tela + badge de tenant sempre visíveis.

### Agrupamento de IA recomendado

| Grupo | Itens | Prioridade nav |
|---|---|---|
| Início | Dashboard (resumo + alertas: cert, DAS, notas falhas) | Alta |
| Fiscal | NFS-e, DAS | Alta |
| Financeiro | Cobranças | Alta |
| Cadastros | Prestadores, Tomadores, Serviços | Média |
| Conta | Certificados, Provedor pagamento, (futuro: WhatsApp canal) | Baixa |

Mobile bottom bar: **Início · NFS-e · Cobranças · Mais** (Mais abre drawer com o resto).

---

## 3. Breakpoints

| Nome | Largura | Comportamento de nav |
|---|---|---|
| Phone | &lt; 640px | Bottom bar + drawer; listas em cards |
| Tablet | 640–1023px | Sidebar colapsável (ícones) ou drawer; tabelas com scroll |
| Desktop | ≥ 1024px | Sidebar completa 240px; tabelas full |

(Hoje o único corte em 980px é insuficiente e destrutivo.)

---

## 4. Protótipos gerados

Arquivo interativo (abrir no browser):

`frontend/prototypes/ux-foundations-nav-responsive.html`

Inclui:

- Seletor de viewport (phone / tablet / desktop) simulando frames  
- Shell com IA proposta  
- Bottom navigation em phone  
- Drawer “Mais”  
- Exemplos Dashboard + lista NFS-e responsiva (tabela → cards)  
- Notas de anotação “problema atual → proposta”

---

## 5. Roadmap de implementação (quando PO autorizar código)

| Fase | Entrega | Esforço estimado |
|---|---|---|
| F0 | Token unificado + sidebar não some sem substituto (drawer) | 2–3 d |
| F1 | Bottom nav mobile + hash/route sync | 2 d |
| F2 | Cadastros embutidos no shell (iframe ou views no SPA) | 3–5 d |
| F3 | Listas: card pattern mobile + sticky actions | 3 d |
| F4 | Command palette “Emitir / Cobrar / Buscar nota” | 2 d |

**Fora do escopo desta análise:** redesign completo de formulários Receita, brand marketing pages, Admin Django.

---

## 6. Critérios de aceite de UX (futuro)

- [ ] Em 390px, usuário navega entre Dashboard / NFS-e / Cobranças sem conhecimento de URL  
- [ ] Em 390px, emite atalho “Nova NFS-e” em ≤ 2 toques a partir de qualquer tela  
- [ ] Breadcrumb ou título sempre alinhado ao módulo ativo  
- [ ] Cadastro de tomador não “abre outro site mental”  
- [ ] Contraste e focus keyboard nos itens de nav (WCAG 2.1 AA baseline)

| Versão | Data | Nota |
|---|---|---|
| 0.1.0 | 2026-08-03 | Análise + protótipo interativo |
