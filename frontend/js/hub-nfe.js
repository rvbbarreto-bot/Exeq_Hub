/** EXEQ Hub — tela Emissão NF-e (modelo 55 B2B) — LLR UI v0.2. */
(function (global) {
  "use strict";

  const A = () => global.HubApi;

  const caches = {
    providers: [],
    customers: [],
    products: [],
    byId: { providers: {}, customers: {}, products: {} },
  };

  let gate = null;
  let statusFilter = "all";
  let listPage = 1;
  const PAGE_SIZE = 20;
  let pageRows = [];
  let pageCount = 0;
  let hasNext = false;
  let hasPrev = false;
  let searchQuery = "";
  let listDays = "30";
  /** @type {any|null} */
  let draftState = null;
  let itemRows = 1;

  function statusBadge(status) {
    const s = String(status || "").toLowerCase();
    if (["draft"].includes(s)) return { cls: "neutral", label: "Rascunho" };
    if (["queued", "submitting", "polling", "cancel_requested"].includes(s)) {
      return { cls: "info", label: "Processando" };
    }
    if (s === "authorized") return { cls: "success", label: "Autorizada" };
    if (s === "rejected") return { cls: "danger", label: "Rejeitada" };
    if (s === "cancelled") return { cls: "neutral", label: "Cancelada" };
    if (s === "failed") return { cls: "danger", label: "Falhou" };
    return { cls: "neutral", label: status || "—" };
  }

  function indexById(list) {
    const map = {};
    for (const item of list) map[item.id] = item;
    return map;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function customerName(id) {
    const c = caches.byId.customers[id];
    return c ? c.name || c.document : String(id || "").slice(0, 8);
  }

  function maskDoc(doc) {
    const d = String(doc || "").replace(/\D/g, "");
    if (d.length === 11) return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.***.***-$4");
    if (d.length === 14) return d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.***/****-$5");
    return doc || "—";
  }

  function formatKey(key) {
    const k = String(key || "");
    if (k.length < 8) return k || "—";
    return k.slice(0, 6) + "…" + k.slice(-6);
  }

  async function loadLookups() {
    const api = A();
    const [providers, customers, products] = await Promise.all([
      api.api("/providers"),
      api.api("/customers"),
      api.api("/nfe/products/"),
    ]);
    caches.providers = api.unwrapList(providers);
    caches.customers = api.unwrapList(customers);
    caches.products = api.unwrapList(products);
    caches.byId.providers = indexById(caches.providers);
    caches.byId.customers = indexById(caches.customers);
    caches.byId.products = indexById(caches.products);
    fillSelects();
  }

  function fillSelects() {
    fillSelect("nfe-provider", caches.providers, (p) => p.trade_name || p.legal_name || p.document);
    fillSelect("nfe-customer", caches.customers, (c) => c.name || c.document);
  }

  function fillSelect(id, list, labelFn) {
    const el = document.getElementById(id);
    if (!el) return;
    const current = el.value;
    el.innerHTML = '<option value="">Selecione…</option>';
    for (const item of list) {
      const opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = labelFn(item);
      el.appendChild(opt);
    }
    if (current) el.value = current;
  }

  function fillProductSelect(selectEl) {
    if (!selectEl) return;
    const current = selectEl.value;
    selectEl.innerHTML = '<option value="">Produto…</option>';
    for (const p of caches.products) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.code} — ${p.description}`;
      selectEl.appendChild(opt);
    }
    if (current) selectEl.value = current;
  }

  async function loadGate() {
    const api = A();
    const box = document.getElementById("nfe-gate-box");
    const btnNew = document.getElementById("btn-emitir-nfe");
    try {
      gate = await api.api("/nfe/gate/");
    } catch (err) {
      gate = { enabled: false, can_create: false, checks: [], error: api.handleApiError(err.body).message };
    }
    if (!box) return;
    if (!gate.enabled) {
      box.innerHTML =
        '<div class="hint">NF-e desabilitada (<code>NFE_ENABLED=false</code>). Ative no ambiente de lab para emitir.</div>';
      if (btnNew) btnNew.disabled = true;
      return;
    }
    const checks = gate.checks || [];
    const lines = checks
      .map((c) => {
        const mark = c.ok ? "✓" : "✗";
        const cls = c.ok ? "success" : "danger";
        return `<span class="badge ${cls}" style="margin:2px">${escapeHtml(mark + " " + c.label)}</span>`;
      })
      .join(" ");
    const meta = [
      `modo=${escapeHtml(gate.http_mode || "—")}`,
      `UF pivot=${escapeHtml(gate.pivot_uf || "SP")}`,
      gate.next_number_estimated != null
        ? `série ${escapeHtml(gate.series)} · próximo estimado ${escapeHtml(gate.next_number_estimated)}`
        : "",
      gate.can_create ? "pode criar: sim" : "pode criar: não",
    ]
      .filter(Boolean)
      .join(" · ");
    const providerId = gate.provider_id || (caches.providers[0] && caches.providers[0].id) || "";
    const seriesForm = `
      <div class="form-grid" style="margin-top:12px;max-width:520px">
        <div class="field">
          <label>Série</label>
          <input id="nfe-cfg-series" type="number" min="1" value="${escapeHtml(gate.series || 1)}">
        </div>
        <div class="field">
          <label>Ambiente</label>
          <select id="nfe-cfg-tp-amb">
            <option value="2" ${(gate.tp_amb || "2") === "2" ? "selected" : ""}>Homologação (2)</option>
            <option value="1" ${gate.tp_amb === "1" ? "selected" : ""}>Produção (1)</option>
          </select>
        </div>
        <div class="field">
          <label>Próximo nº (estimado)</label>
          <input id="nfe-cfg-next" type="number" min="1" value="${escapeHtml(gate.next_number_estimated || 1)}">
        </div>
        <div class="field" style="align-self:end">
          <button type="button" class="btn btn-ghost" id="btn-nfe-save-series">Salvar série</button>
        </div>
      </div>
      <input type="hidden" id="nfe-cfg-provider" value="${escapeHtml(providerId)}">
      <div class="hint" style="margin-top:8px">T6 — contador por emitente/ambiente. Em stub a série auto-cria no emit; em HTTP cadastre antes.</div>
    `;
    box.innerHTML = `<div style="margin-bottom:8px">${lines}</div><div class="hint">${meta}</div>${seriesForm}`;
    if (btnNew) btnNew.disabled = !gate.can_create;
    const saveBtn = document.getElementById("btn-nfe-save-series");
    if (saveBtn) {
      saveBtn.onclick = () => saveSeriesConfig();
    }
  }

  async function saveSeriesConfig() {
    const api = A();
    const provider_id =
      (document.getElementById("nfe-cfg-provider") || {}).value ||
      (caches.providers[0] && caches.providers[0].id);
    if (!provider_id) {
      api.toast("Cadastre um prestador antes de configurar série.", "danger");
      return;
    }
    const series = Number((document.getElementById("nfe-cfg-series") || {}).value || 1);
    const tp_amb = String((document.getElementById("nfe-cfg-tp-amb") || {}).value || "2");
    const next_number = Number((document.getElementById("nfe-cfg-next") || {}).value || 1);
    try {
      await api.api("/nfe/config/", {
        method: "PUT",
        body: { provider_id, series, tp_amb, next_number, is_active: true },
      });
      api.toast("Série NF-e salva", "success");
      await loadGate();
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  async function loadList() {
    const api = A();
    const tbody = document.getElementById("tbody-nfe");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7">Carregando…</td></tr>';
    try {
      if (!gate) await loadGate();
      else await loadGate();
      if (!caches.customers.length) await loadLookups();
      if (!gate.enabled) {
        tbody.innerHTML = '<tr><td colspan="7">Feature NF-e desligada.</td></tr>';
        return;
      }
      const qEl = document.getElementById("nfe-search-q");
      const daysEl = document.getElementById("nfe-filter-days");
      if (qEl) searchQuery = (qEl.value || "").trim();
      if (daysEl) listDays = String(daysEl.value || "30");
      const params = new URLSearchParams({
        page: String(listPage),
        page_size: String(PAGE_SIZE),
      });
      if (statusFilter && statusFilter !== "all") {
        params.set("status", statusFilter);
      }
      if (searchQuery) params.set("q", searchQuery);
      if (listDays === "all") params.set("days", "0");
      else if (listDays) params.set("days", listDays);
      const data = await api.api(`/nfe/invoices/?${params.toString()}`);
      const page = api.unwrapPage(data);
      pageRows = page.results || [];
      pageCount = page.count || pageRows.length;
      hasNext = Boolean(page.next);
      hasPrev = Boolean(page.previous);
      renderTabs();
      if (!pageRows.length) {
        tbody.innerHTML = '<tr><td colspan="7">Nenhuma NF-e no filtro atual.</td></tr>';
      } else {
        tbody.innerHTML = "";
        for (const row of pageRows) tbody.appendChild(renderRow(row));
      }
      updatePager();
    } catch (err) {
      const { message } = api.handleApiError(err.body);
      tbody.innerHTML = `<tr><td colspan="7">${escapeHtml(message)}</td></tr>`;
    }
  }

  function renderTabs() {
    const root = document.getElementById("tabs-nfe");
    if (!root) return;
    const defs = [
      ["all", "Todas"],
      ["draft", "Rascunho"],
      ["processing", "Processando"],
      ["authorized", "Autorizadas"],
      ["rejected", "Rejeitadas"],
      ["cancelled", "Canceladas"],
      ["failed", "Falhas"],
    ];
    root.innerHTML = "";
    for (const [key, label] of defs) {
      const div = document.createElement("div");
      div.className = "tab" + (statusFilter === key ? " active" : "");
      div.textContent = label;
      div.addEventListener("click", () => {
        if (statusFilter === key) return;
        statusFilter = key;
        listPage = 1;
        loadList();
      });
      root.appendChild(div);
    }
  }

  function updatePager() {
    const pager = document.getElementById("pager-nfe-label");
    const prev = document.getElementById("btn-nfe-prev");
    const next = document.getElementById("btn-nfe-next");
    if (pager) {
      pager.textContent =
        pageCount === 0
          ? "Nenhuma nota"
          : `Página ${listPage} · ${pageRows.length} item(ns) nesta página`;
    }
    if (prev) prev.disabled = !hasPrev;
    if (next) next.disabled = !hasNext;
  }

  function renderRow(row) {
    const api = A();
    const tr = document.createElement("tr");
    const badge = statusBadge(row.status);
    const num =
      row.number != null
        ? `${row.series}/${row.number}`
        : `${row.series}/—`;
    const actions = row.allowed_actions || [];
    tr.innerHTML = `
      <td>
        <div class="cell-title">${escapeHtml(num)}</div>
        <div class="cell-sub">${escapeHtml(String(row.idempotency_key || "").slice(0, 12))}</div>
      </td>
      <td>${escapeHtml(row.issue_date || "—")}</td>
      <td>
        <div class="cell-title">${escapeHtml(customerName(row.customer))}</div>
        <div class="cell-sub">${escapeHtml(maskDoc(caches.byId.customers[row.customer]?.document))}</div>
      </td>
      <td class="num">${escapeHtml(api.formatBrlFromCents(row.total_cents))}</td>
      <td><span class="badge ${badge.cls}">${badge.label}</span></td>
      <td class="cell-sub">${escapeHtml(formatKey(row.access_key))}</td>
      <td class="row-actions"></td>`;
    const cell = tr.querySelector(".row-actions");
    if (actions.includes("emit") || actions.includes("validate")) {
      cell.appendChild(iconBtn("Transmitir", "emit", () => openDraft(row)));
    }
    if (actions.includes("clone")) {
      cell.appendChild(iconBtn("Corrigir (clone)", "clone", () => cloneInvoice(row)));
    }
    if (actions.includes("discard")) {
      cell.appendChild(iconBtn("Descartar rascunho", "discard", () => discardInvoice(row)));
    }
    if (actions.includes("cancel")) {
      cell.appendChild(iconBtn("Cancelar", "cancel", () => openCancel(row)));
    }
    if (actions.includes("download_xml")) {
      cell.appendChild(iconBtn("Baixar XML", "download_xml", () => downloadArtifact(row, "xml")));
    }
    if (actions.includes("download_pdf")) {
      cell.appendChild(iconBtn("Baixar DANFE PDF", "download_pdf", () => downloadArtifact(row, "pdf")));
    }
    cell.appendChild(iconBtn("Detalhe", "poll", () => openDetail(row)));
    return tr;
  }

  async function discardInvoice(row) {
    const api = A();
    if (!row || !row.id) return;
    if (!confirm("Descartar este rascunho? Não pode ser desfeito.")) return;
    try {
      await api.api(`/nfe/invoices/${row.id}/discard`, { method: "POST", body: {} });
      api.toast("Rascunho descartado", "success");
      await loadList();
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  async function cloneInvoice(row) {
    const api = A();
    if (!row || !row.id) return;
    try {
      const clone = await api.api(`/nfe/invoices/${row.id}/clone`, {
        method: "POST",
        body: { idempotency_key: crypto.randomUUID() },
      });
      api.toast("Novo rascunho criado a partir da rejeitada", "success");
      await loadList();
      openDraft(clone);
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  function iconBtn(title, kind, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "icon-btn";
    btn.title = title;
    const icons = {
      emit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 12h14M12 5l7 7-7 7"/></svg>',
      cancel:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>',
      clone:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="11" height="11" rx="1"/><path d="M5 15V5h10"/></svg>',
      discard:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M9 7V5h6v2M10 11v6M14 11v6M6 7l1 12h10l1-12"/></svg>',
      download_xml:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 19h14"/><path d="M8 6h8" opacity=".35"/></svg>',
      download_pdf:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M12 12v5"/><path d="M9.5 14.5 12 17l2.5-2.5"/></svg>',
      poll: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>',
    };
    btn.innerHTML = icons[kind] || icons.poll;
    btn.addEventListener("click", onClick);
    return btn;
  }

  async function downloadArtifact(row, kind) {
    const api = A();
    if (!row || !row.id) return;
    const path =
      kind === "pdf"
        ? `/nfe/invoices/${row.id}/artifacts/pdf`
        : `/nfe/invoices/${row.id}/artifacts/xml`;
    try {
      const blob = await api.api(path, { method: "GET", blob: true });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const key = (row.access_key || row.id || "nfe").toString().slice(0, 44);
      a.download = kind === "pdf" ? `danfe-${key}.pdf` : `nfe-${key}.xml`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      api.toast(kind === "pdf" ? "DANFE baixado" : "XML baixado", "success");
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  function renderItemRows() {
    const host = document.getElementById("nfe-items-host");
    if (!host) return;
    host.innerHTML = "";
    for (let i = 0; i < itemRows; i++) {
      const wrap = document.createElement("div");
      wrap.className = "form-grid nfe-item-row";
      wrap.dataset.idx = String(i);
      wrap.innerHTML = `
        <div class="field">
          <label>Produto</label>
          <select class="nfe-item-product" data-idx="${i}"></select>
        </div>
        <div class="field">
          <label>Qtd</label>
          <input class="nfe-item-qty" data-idx="${i}" type="text" value="1" inputmode="decimal">
        </div>
        <div class="field">
          <label>CFOP (opc.)</label>
          <input class="nfe-item-cfop" data-idx="${i}" type="text" maxlength="4" placeholder="5102">
        </div>`;
      host.appendChild(wrap);
      fillProductSelect(wrap.querySelector(".nfe-item-product"));
    }
  }

  function collectItems() {
    const items = [];
    document.querySelectorAll(".nfe-item-product").forEach((sel) => {
      const idx = sel.dataset.idx;
      const product_id = sel.value;
      if (!product_id) return;
      const qtyEl = document.querySelector(`.nfe-item-qty[data-idx="${idx}"]`);
      const cfopEl = document.querySelector(`.nfe-item-cfop[data-idx="${idx}"]`);
      const row = {
        product_id,
        quantity: (qtyEl && qtyEl.value) || "1",
      };
      if (cfopEl && cfopEl.value.trim()) row.cfop = cfopEl.value.trim();
      items.push(row);
    });
    return items;
  }

  async function openCreateModal() {
    const api = A();
    if (gate && !gate.can_create) {
      api.toast("Pré-condições NF-e incompletas. Veja o gate acima.", "danger");
      return;
    }
    draftState = null;
    itemRows = 1;
    const form = document.getElementById("form-nfe");
    if (form) form.reset();
    document.getElementById("nfe-status-line").textContent = "";
    document.getElementById("nfe-validate-out").textContent = "";
    await loadLookups();
    renderItemRows();
    if (caches.providers[0]) {
      const el = document.getElementById("nfe-provider");
      if (el) el.value = caches.providers[0].id;
    }
    api.openModal("modal-nfe");
  }

  async function openDraft(row) {
    const api = A();
    draftState = row;
    itemRows = Math.max(1, (row.items || []).length || 1);
    await loadLookups();
    renderItemRows();
    const form = document.getElementById("form-nfe");
    if (form) {
      if (form.provider_id) form.provider_id.value = row.provider;
      if (form.customer_id) form.customer_id.value = row.customer;
      if (form.nature_operation) form.nature_operation.value = row.nature_operation || "VENDA";
    }
    const items = row.items || [];
    items.forEach((it, i) => {
      const sel = document.querySelector(`.nfe-item-product[data-idx="${i}"]`);
      const qty = document.querySelector(`.nfe-item-qty[data-idx="${i}"]`);
      const cfop = document.querySelector(`.nfe-item-cfop[data-idx="${i}"]`);
      if (sel && it.product) sel.value = it.product;
      if (qty) qty.value = it.quantity || "1";
      if (cfop && it.cfop) cfop.value = it.cfop;
    });
    document.getElementById("nfe-status-line").textContent =
      `Rascunho ${row.id.slice(0, 8)} · status ${row.status} · v${row.version}`;
    api.openModal("modal-nfe");
  }

  async function ensureDraft() {
    const api = A();
    const form = document.getElementById("form-nfe");
    if (draftState && draftState.id) return draftState;
    const body = {
      idempotency_key: crypto.randomUUID(),
      provider_id: form.provider_id.value,
      customer_id: form.customer_id.value,
      nature_operation: form.nature_operation.value || "VENDA",
      series: 1,
      ind_ie_dest: form.ind_ie_dest.value || "9",
    };
    if (!body.provider_id || !body.customer_id) {
      throw new Error("Selecione emitente e destinatário");
    }
    const inv = await api.api("/nfe/invoices/", { method: "POST", body });
    draftState = inv;
    return inv;
  }

  async function saveItems() {
    const api = A();
    const inv = await ensureDraft();
    const items = collectItems();
    if (!items.length) throw new Error("Inclua ao menos um item com produto");
    const updated = await api.api(`/nfe/invoices/${inv.id}/items`, {
      method: "PUT",
      body: { version: inv.version, items },
    });
    draftState = updated;
    return updated;
  }

  async function onValidate() {
    const api = A();
    const out = document.getElementById("nfe-validate-out");
    try {
      const inv = await saveItems();
      const res = await api.api(`/nfe/invoices/${inv.id}/validate`, { method: "POST", body: {} });
      draftState = res.invoice || inv;
      const v = res.validation || {};
      if (v.ok) {
        out.textContent = `OK · total ${api.formatBrlFromCents(v.totals?.total_cents)} · engine ${v.totals?.tax_engine_version || ""}`;
        api.toast("Validação OK", "success");
      } else {
        out.textContent = "Erros: " + JSON.stringify(v.field_errors || []);
        api.toast("Validação com erros", "danger");
      }
    } catch (err) {
      const msg = err.message || api.handleApiError(err.body).message;
      out.textContent = msg;
      api.toast(msg, "danger");
    }
  }

  async function onEmitConfirm(ev) {
    ev.preventDefault();
    const api = A();
    const statusEl = document.getElementById("nfe-status-line");
    try {
      if (!draftState) await saveItems();
      else await saveItems();
      const inv = draftState;
      statusEl.textContent = "Transmitindo…";
      const res = await api.api(`/nfe/invoices/${inv.id}/emit`, {
        method: "POST",
        body: { version: inv.version },
      });
      draftState = res;
      statusEl.textContent = `Status: ${res.status} · chave ${formatKey(res.access_key)} · protocolo ${res.protocol || "—"}`;
      if (res.status === "authorized") {
        api.toast("NF-e autorizada (stub ou SEFAZ)", "success");
        api.closeModal("modal-nfe-confirm");
        api.closeModal("modal-nfe");
        loadList();
      } else {
        api.toast(`Emitiu com status ${res.status}`, res.status === "rejected" ? "danger" : "warning");
        loadList();
      }
    } catch (err) {
      const { message } = api.handleApiError(err.body);
      statusEl.textContent = message;
      api.toast(message, "danger");
    }
  }

  function openEmitConfirm() {
    const api = A();
    const amb = gate?.tp_amb === "1" ? "PRODUÇÃO" : "HOMOLOGAÇÃO";
    const mode = gate?.http_mode || "stub";
    document.getElementById("nfe-confirm-text").textContent =
      `Transmitir esta NF-e no ambiente ${amb} (modo ${mode})? O número será reservado no Hub.`;
    api.openModal("modal-nfe-confirm");
  }

  function openCancel(row) {
    const form = document.getElementById("form-nfe-cancel");
    if (form) {
      form.dataset.id = row.id;
      form.justificativa.value = "";
    }
    document.getElementById("nfe-cancel-summary").textContent =
      `NF-e ${row.series}/${row.number || "—"} · ${formatKey(row.access_key)}`;
    A().openModal("modal-nfe-cancel");
  }

  async function submitCancel(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-nfe-cancel");
    const id = form.dataset.id;
    try {
      await api.api(`/nfe/invoices/${id}/cancel`, {
        method: "POST",
        body: { justificativa: form.justificativa.value },
      });
      api.toast("Cancelamento processado", "success");
      api.closeModal("modal-nfe-cancel");
      loadList();
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  async function openDetail(row) {
    const api = A();
    const body = document.getElementById("nfe-detail-body");
    if (!body || !row || !row.id) return;
    body.innerHTML = '<div class="hint">Carregando detalhe…</div>';
    api.openModal("modal-nfe-detail");
    let detail = row;
    let events = [];
    try {
      detail = await api.api(`/nfe/invoices/${row.id}/`);
      const evPayload = await api.api(`/nfe/invoices/${row.id}/events`);
      events = (evPayload && evPayload.events) || [];
    } catch (err) {
      body.innerHTML = `<div class="hint">${escapeHtml(api.handleApiError(err.body).message)}</div>`;
      return;
    }
    const actions = (detail.allowed_actions || []).join(", ") || "—";
    const arts = detail.artifacts || {};
    const timeline = events
      .map((ev) => {
        const meta = ev.metadata || {};
        const extra = [];
        if (meta.cStat) extra.push(`cStat=${meta.cStat}`);
        if (meta.xMotivo) extra.push(String(meta.xMotivo).slice(0, 80));
        if (meta.reason) extra.push(meta.reason);
        const when = (ev.occurred_at || "").replace("T", " ").slice(0, 19);
        return `<li><code>${escapeHtml(when)}</code> ${escapeHtml(ev.from_status || "—")} → <b>${escapeHtml(
          ev.to_status || ""
        )}</b> <span class="cell-sub">(${escapeHtml(ev.actor || "—")})${
          extra.length ? " · " + escapeHtml(extra.join(" · ")) : ""
        }</span></li>`;
      })
      .join("");
    body.innerHTML = `
      <div class="hint">Status: <b>${escapeHtml(detail.status)}</b> · v${escapeHtml(detail.version)}</div>
      <div class="hint">Série/nº: ${escapeHtml(detail.series)}/${escapeHtml(detail.number ?? "—")}</div>
      <div class="hint">Emissão: ${escapeHtml(detail.issue_date || "—")}</div>
      <div class="hint">Chave: <code>${escapeHtml(detail.access_key || "—")}</code></div>
      <div class="hint">Protocolo: ${escapeHtml(detail.protocol || "—")}</div>
      <div class="hint">Total: ${escapeHtml(api.formatBrlFromCents(detail.total_cents))}</div>
      <div class="hint">Rejeição: ${escapeHtml(detail.rejection_code || "")} ${escapeHtml(
      detail.rejection_message || ""
    )}</div>
      <div class="hint">Artefatos: XML=${arts.xml_authorized ? "sim" : "não"} · DANFE=${
      arts.danfe_pdf ? "sim" : "não"
    }</div>
      <div class="hint">allowed_actions: ${escapeHtml(actions)}</div>
      <div class="hint">correlation: ${escapeHtml(detail.correlation_id || "")}</div>
      <div class="row-actions" id="nfe-detail-downloads" style="margin-top:12px;gap:8px;display:flex;flex-wrap:wrap"></div>
      <h4 style="margin:16px 0 8px;font-size:0.95rem">Timeline</h4>
      <ul id="nfe-detail-timeline" class="hint" style="padding-left:18px;margin:0">${
        timeline || "<li>Sem eventos</li>"
      }</ul>`;
    const host = document.getElementById("nfe-detail-downloads");
    if (host) {
      const acts = detail.allowed_actions || [];
      if (acts.includes("download_xml")) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn btn-ghost";
        b.textContent = "Baixar XML";
        b.addEventListener("click", () => downloadArtifact(detail, "xml"));
        host.appendChild(b);
      }
      if (acts.includes("download_pdf")) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn btn-primary";
        b.textContent = "Baixar DANFE PDF";
        b.addEventListener("click", () => downloadArtifact(detail, "pdf"));
        host.appendChild(b);
      }
    }
  }

  async function onCreateProduct(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-nfe-product");
    try {
      await api.api("/nfe/products/", {
        method: "POST",
        body: {
          code: form.code.value.trim(),
          description: form.description.value.trim(),
          ncm: form.ncm.value.trim(),
          unit: form.unit.value || "UN",
          unit_price_cents: A().reaisToCents(form.price_reais.value),
          csosn: form.csosn.value || "102",
          origin: "0",
          cfop_internal: form.cfop.value || "5102",
        },
      });
      api.toast("Produto fiscal criado", "success");
      api.closeModal("modal-nfe-product");
      form.reset();
      await loadLookups();
      renderProductsTable();
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  function renderProductsTable() {
    const tbody = document.getElementById("tbody-nfe-products");
    if (!tbody) return;
    if (!caches.products.length) {
      tbody.innerHTML = '<tr><td colspan="5">Nenhum produto fiscal.</td></tr>';
      return;
    }
    tbody.innerHTML = "";
    for (const p of caches.products) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(p.code)}</td>
        <td>${escapeHtml(p.description)}</td>
        <td>${escapeHtml(p.ncm)}</td>
        <td class="num">${escapeHtml(A().formatBrlFromCents(p.unit_price_cents))}</td>
        <td>${escapeHtml(p.csosn || p.icms_cst || "—")}</td>`;
      tbody.appendChild(tr);
    }
  }

  function bind() {
    const btn = document.getElementById("btn-emitir-nfe");
    if (btn) btn.addEventListener("click", openCreateModal);
    const btnProd = document.getElementById("btn-nfe-product");
    if (btnProd) {
      btnProd.addEventListener("click", () => {
        A().openModal("modal-nfe-product");
      });
    }
    const addItem = document.getElementById("btn-nfe-add-item");
    if (addItem) {
      addItem.addEventListener("click", () => {
        itemRows += 1;
        renderItemRows();
      });
    }
    const btnVal = document.getElementById("btn-nfe-validate");
    if (btnVal) btnVal.addEventListener("click", onValidate);
    const btnEmit = document.getElementById("btn-nfe-emit");
    if (btnEmit) btnEmit.addEventListener("click", openEmitConfirm);
    const formConfirm = document.getElementById("form-nfe-confirm");
    if (formConfirm) formConfirm.addEventListener("submit", onEmitConfirm);
    const cancelForm = document.getElementById("form-nfe-cancel");
    if (cancelForm) cancelForm.addEventListener("submit", submitCancel);
    const prodForm = document.getElementById("form-nfe-product");
    if (prodForm) prodForm.addEventListener("submit", onCreateProduct);
    const price = document.getElementById("nfe-product-price");
    if (price) A().bindMoneyMask(price);
    const prev = document.getElementById("btn-nfe-prev");
    const next = document.getElementById("btn-nfe-next");
    if (prev) {
      prev.addEventListener("click", () => {
        if (!hasPrev || listPage <= 1) return;
        listPage -= 1;
        loadList();
      });
    }
    if (next) {
      next.addEventListener("click", () => {
        if (!hasNext) return;
        listPage += 1;
        loadList();
      });
    }
    const searchBtn = document.getElementById("btn-nfe-search");
    if (searchBtn) {
      searchBtn.addEventListener("click", () => {
        listPage = 1;
        loadList();
      });
    }
    const searchInput = document.getElementById("nfe-search-q");
    if (searchInput) {
      searchInput.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          listPage = 1;
          loadList();
        }
      });
    }
    const daysEl = document.getElementById("nfe-filter-days");
    if (daysEl) {
      daysEl.addEventListener("change", () => {
        listPage = 1;
        loadList();
      });
    }
  }

  async function loadScreen() {
    await loadGate();
    await loadLookups();
    renderProductsTable();
    await loadList();
  }

  global.HubNfe = {
    bind,
    loadList,
    loadScreen,
    loadGate,
  };
})(window);
