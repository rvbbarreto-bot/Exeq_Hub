/** EXEQ Hub — tela Emissão NFS-e (#screen-nfse). */
(function (global) {
  "use strict";

  const A = () => global.HubApi;

  /** @type {Record<string, any>} */
  const caches = {
    providers: [],
    customers: [],
    services: [],
    profiles: [],
    byId: { providers: {}, customers: {}, services: {}, profiles: {} },
  };

  let nfIdempotencyKey = null;
  let pollTimer = null;
  let statusFilter = "all";
  let listPage = 1;
  const PAGE_SIZE = 20;
  /** @type {any[]} */
  let pageRows = [];
  /** @type {{ total: number, by_status: Record<string, number> }} */
  let summary = { total: 0, by_status: {} };
  let hasNext = false;
  let hasPrev = false;
  let pageCount = 0;

  /** Autocomplete Serviço */
  const serviceAc = {
    items: /** @type {any[]} */ ([]),
    filtered: /** @type {any[]} */ ([]),
    activeIndex: -1,
    open: false,
    maxVisible: 60,
    bound: false,
  };

  const TERMINAL = new Set(["authorized", "rejected", "cancelled", "failed"]);

  function statusBadge(status) {
    const s = String(status || "").toLowerCase();
    if (["draft", "pending_tax", "queued", "submitting", "polling"].includes(s)) {
      return { cls: "info", label: "Em processamento" };
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

  async function loadLookups() {
    const api = A();
    const [providers, customers, services, profiles] = await Promise.all([
      api.api("/providers"),
      api.api("/customers"),
      api.api("/services"),
      api.api("/fiscal/profiles"),
    ]);
    caches.providers = api.unwrapList(providers);
    caches.customers = api.unwrapList(customers);
    caches.services = api.unwrapList(services);
    caches.profiles = api.unwrapList(profiles);
    caches.byId.providers = indexById(caches.providers);
    caches.byId.customers = indexById(caches.customers);
    caches.byId.services = indexById(caches.services);
    caches.byId.profiles = indexById(caches.profiles);
    fillSelects();
  }

  function fillSelects() {
    fillSelect("nf-provider", caches.providers, (p) => p.trade_name || p.legal_name || p.document);
    fillSelect("nf-customer", caches.customers, (c) => c.name || c.document);
    fillSelect("nf-profile", caches.profiles, (p) => p.name || p.id);
    setServiceItems(caches.services);
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

  /** item.subitem.desdobro — ex.: 01.03.01 */
  function formatNationalDisplayCode(codigo) {
    const digits = String(codigo || "").replace(/\D/g, "");
    if (digits.length < 5) return String(codigo || "").trim();
    const desdobro = digits.slice(-2);
    const subitem = digits.slice(-4, -2);
    const item = digits.slice(0, -4) || "0";
    return (
      String(Number(item)).padStart(2, "0") +
      "." +
      subitem.padStart(2, "0") +
      "." +
      desdobro.padStart(2, "0")
    );
  }

  function serviceCode(s) {
    if (!s) return "";
    const raw = s.codigo_tributacao_nacional_iss || s.service_code || "";
    return formatNationalDisplayCode(raw);
  }

  function serviceLabel(s) {
    if (!s) return "—";
    if (s.display_label) return s.display_label;
    const code = serviceCode(s);
    const desc = (s.description || "").trim();
    if (code && desc) return code + " - " + desc;
    return desc || code || s.service_code || "—";
  }

  function normalizeSearch(text) {
    return String(text || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function serviceSearchBlob(s) {
    const code = serviceCode(s);
    const raw = s.codigo_tributacao_nacional_iss || s.service_code || "";
    return normalizeSearch(
      [code, raw, s.service_code, s.lc116_item, s.description, s.display_label]
        .filter(Boolean)
        .join(" ")
    );
  }

  function customerName(id) {
    const c = caches.byId.customers[id];
    return c ? c.name || c.document : String(id || "").slice(0, 8);
  }

  function serviceName(id) {
    return serviceLabel(caches.byId.services[id]);
  }

  function resolveIbgeCode(providerId) {
    const p = caches.byId.providers[providerId];
    const addr = (p && p.address) || {};
    const raw = addr.codigo_municipio_ibge || addr.ibge || "";
    const digits = String(raw).replace(/\D/g, "").slice(0, 7);
    return digits.length === 7 ? digits : "3504107";
  }

  function serviceComboEls() {
    return {
      root: document.getElementById("nf-service-combo"),
      hidden: document.getElementById("nf-service"),
      input: document.getElementById("nf-service-search"),
      list: document.getElementById("nf-service-list"),
      clear: document.getElementById("nf-service-clear"),
    };
  }

  function setServiceItems(list) {
    serviceAc.items = Array.isArray(list) ? list.slice() : [];
    const { hidden } = serviceComboEls();
    const selectedId = hidden && hidden.value;
    if (selectedId && caches.byId.services[selectedId]) {
      syncServiceInputLabel(caches.byId.services[selectedId]);
    }
  }

  function resetServiceCombo() {
    const { root, hidden, input, list } = serviceComboEls();
    if (hidden) hidden.value = "";
    if (input) input.value = "";
    if (root) root.classList.remove("has-value", "is-open");
    if (list) {
      list.innerHTML = "";
      list.hidden = true;
    }
    serviceAc.filtered = [];
    serviceAc.activeIndex = -1;
    serviceAc.open = false;
    if (input) input.setAttribute("aria-expanded", "false");
  }

  function syncServiceInputLabel(service) {
    const { root, hidden, input } = serviceComboEls();
    if (!service || !hidden || !input) return;
    hidden.value = service.id;
    input.value = serviceLabel(service);
    if (root) root.classList.add("has-value");
  }

  function selectService(service) {
    if (!service) return;
    syncServiceInputLabel(service);
    closeServiceList();
  }

  function clearServiceSelection() {
    resetServiceCombo();
    const { input } = serviceComboEls();
    if (input) input.focus();
  }

  function openServiceList() {
    const { root, input, list } = serviceComboEls();
    if (!root || !list || !input) return;
    serviceAc.open = true;
    root.classList.add("is-open");
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function closeServiceList() {
    const { root, input, list } = serviceComboEls();
    serviceAc.open = false;
    serviceAc.activeIndex = -1;
    if (root) root.classList.remove("is-open");
    if (list) list.hidden = true;
    if (input) input.setAttribute("aria-expanded", "false");
  }

  function filterServices(query) {
    const q = normalizeSearch(query);
    const qDigits = q.replace(/\D/g, "");
    let list = serviceAc.items;
    if (q) {
      list = serviceAc.items.filter((s) => {
        const blob = serviceSearchBlob(s);
        if (blob.includes(q)) return true;
        if (qDigits.length >= 2) {
          const raw = String(s.codigo_tributacao_nacional_iss || s.service_code || "").replace(
            /\D/g,
            ""
          );
          const code = serviceCode(s).replace(/\D/g, "");
          if (raw.includes(qDigits) || code.includes(qDigits)) return true;
        }
        return false;
      });
    }
    serviceAc.filtered = list;
    serviceAc.activeIndex = list.length ? 0 : -1;
    renderServiceList();
    openServiceList();
  }

  function renderServiceList() {
    const { list } = serviceComboEls();
    if (!list) return;
    list.innerHTML = "";
    const total = serviceAc.filtered.length;
    if (!total) {
      const empty = document.createElement("li");
      empty.className = "ac-combo-empty";
      empty.textContent = "Nenhum serviço encontrado.";
      list.appendChild(empty);
      return;
    }
    const slice = serviceAc.filtered.slice(0, serviceAc.maxVisible);
    slice.forEach((s, idx) => {
      const li = document.createElement("li");
      li.setAttribute("role", "presentation");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ac-combo-option" + (idx === serviceAc.activeIndex ? " is-active" : "");
      btn.setAttribute("role", "option");
      btn.setAttribute("data-id", s.id);
      btn.setAttribute("aria-selected", idx === serviceAc.activeIndex ? "true" : "false");
      const code = document.createElement("span");
      code.className = "ac-combo-code";
      code.textContent = serviceCode(s) || s.service_code || "—";
      const desc = document.createElement("span");
      desc.className = "ac-combo-desc";
      desc.textContent = (s.description || "").trim() || serviceLabel(s);
      btn.appendChild(code);
      btn.appendChild(desc);
      btn.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        selectService(s);
      });
      li.appendChild(btn);
      list.appendChild(li);
    });
    if (total > serviceAc.maxVisible) {
      const meta = document.createElement("li");
      meta.className = "ac-combo-meta";
      meta.textContent =
        "Mostrando " + serviceAc.maxVisible + " de " + total + ". Refine a busca.";
      list.appendChild(meta);
    }
  }

  function moveServiceActive(delta) {
    if (!serviceAc.filtered.length) return;
    const max = Math.min(serviceAc.filtered.length, serviceAc.maxVisible) - 1;
    let next = serviceAc.activeIndex + delta;
    if (next < 0) next = max;
    if (next > max) next = 0;
    serviceAc.activeIndex = next;
    renderServiceList();
    const { list } = serviceComboEls();
    const active = list && list.querySelector(".ac-combo-option.is-active");
    if (active && typeof active.scrollIntoView === "function") {
      active.scrollIntoView({ block: "nearest" });
    }
  }

  function commitServiceFromInput() {
    const { hidden, input } = serviceComboEls();
    if (!hidden || !input) return;
    if (hidden.value && caches.byId.services[hidden.value]) {
      syncServiceInputLabel(caches.byId.services[hidden.value]);
      return;
    }
    const q = normalizeSearch(input.value);
    if (!q) {
      resetServiceCombo();
      return;
    }
    const exact = serviceAc.items.find((s) => {
      const label = normalizeSearch(serviceLabel(s));
      const code = normalizeSearch(serviceCode(s));
      return label === q || code === q || normalizeSearch(s.service_code) === q;
    });
    if (exact) {
      selectService(exact);
      return;
    }
    if (serviceAc.filtered.length === 1) {
      selectService(serviceAc.filtered[0]);
      return;
    }
    input.value = "";
    hidden.value = "";
    const { root } = serviceComboEls();
    if (root) root.classList.remove("has-value");
  }

  function bindServiceAutocomplete() {
    if (serviceAc.bound) return;
    const { root, input, clear } = serviceComboEls();
    if (!root || !input) return;
    serviceAc.bound = true;

    input.addEventListener("focus", () => {
      filterServices(input.value);
    });
    input.addEventListener("input", () => {
      const { hidden, root: r } = serviceComboEls();
      if (hidden) hidden.value = "";
      if (r) r.classList.remove("has-value");
      filterServices(input.value);
    });
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        if (!serviceAc.open) filterServices(input.value);
        else moveServiceActive(1);
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        if (serviceAc.open) moveServiceActive(-1);
      } else if (ev.key === "Enter") {
        if (serviceAc.open && serviceAc.activeIndex >= 0) {
          ev.preventDefault();
          const s = serviceAc.filtered[serviceAc.activeIndex];
          if (s) selectService(s);
        }
      } else if (ev.key === "Escape") {
        closeServiceList();
      }
    });
    input.addEventListener("blur", () => {
      setTimeout(() => {
        closeServiceList();
        commitServiceFromInput();
      }, 120);
    });
    if (clear) {
      clear.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        clearServiceSelection();
      });
    }
  }

  async function loadSummary() {
    try {
      summary = await A().api("/nf-issue/summary/");
      if (!summary || typeof summary !== "object") {
        summary = { total: 0, by_status: {} };
      }
      if (!summary.by_status) summary.by_status = {};
    } catch {
      summary = { total: 0, by_status: {} };
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => renderCharts());
    });
  }

  function renderCharts() {
    if (!global.HubCharts) return;
    const by = summary.by_status || {};
    const col = HubCharts.palette();
    const processing =
      (by.draft || 0) +
      (by.pending_tax || 0) +
      (by.queued || 0) +
      (by.submitting || 0) +
      (by.polling || 0);
    HubCharts.renderStatusBars("chartNfseStatus", {
      labels: ["Autorizada", "Em processamento", "Rejeitada", "Cancelada", "Falhou"],
      values: [
        by.authorized || 0,
        processing,
        by.rejected || 0,
        by.cancelled || 0,
        by.failed || 0,
      ],
      colors: [col.success, col.info, col.danger, col.neutral, col.warning],
    });
  }

  async function loadList() {
    const api = A();
    const tbody = document.getElementById("tbody-nfse");
    const pager = document.getElementById("pager-nfse-label");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6">Carregando…</td></tr>';
    try {
      if (!caches.customers.length) await loadLookups();
      await loadSummary();
      const params = new URLSearchParams({
        page: String(listPage),
        page_size: String(PAGE_SIZE),
      });
      if (statusFilter && statusFilter !== "all") {
        params.set("status", statusFilter);
      }
      const data = await api.api(`/nf-issue/?${params.toString()}`);
      const page = api.unwrapPage(data);
      pageRows = page.results;
      pageCount = page.count;
      hasNext = Boolean(page.next);
      hasPrev = Boolean(page.previous);
      renderTabs();
      if (!pageRows.length) {
        tbody.innerHTML = '<tr><td colspan="6">Nenhuma NFS-e encontrada.</td></tr>';
      } else {
        tbody.innerHTML = "";
        for (const row of pageRows) {
          tbody.appendChild(renderRow(row));
        }
      }
      updatePagerLabel();
    } catch (err) {
      const { message } = api.handleApiError(err.body);
      tbody.innerHTML = `<tr><td colspan="6">${escapeHtml(message)}</td></tr>`;
    }
  }

  function updatePagerLabel() {
    const pager = document.getElementById("pager-nfse-label");
    const prev = document.getElementById("btn-nfse-prev");
    const next = document.getElementById("btn-nfse-next");
    const from = pageCount === 0 ? 0 : (listPage - 1) * PAGE_SIZE + 1;
    const to = Math.min(listPage * PAGE_SIZE, pageCount);
    if (pager) {
      pager.textContent =
        pageCount === 0 ? "Nenhuma nota" : `Exibindo ${from}–${to} de ${pageCount}`;
    }
    if (prev) prev.disabled = !hasPrev;
    if (next) next.disabled = !hasNext;
  }

  function renderTabs() {
    const root = document.getElementById("tabs-nfse");
    if (!root) return;
    const by = summary.by_status || {};
    const processing =
      (by.draft || 0) +
      (by.pending_tax || 0) +
      (by.queued || 0) +
      (by.submitting || 0) +
      (by.polling || 0);
    const defs = [
      ["all", "Todas", summary.total || 0],
      ["processing", "Em processamento", processing],
      ["authorized", "Autorizadas", by.authorized || 0],
      ["rejected", "Rejeitadas", by.rejected || 0],
      ["cancelled", "Canceladas", by.cancelled || 0],
      ["failed", "Falhas", by.failed || 0],
    ];
    root.innerHTML = "";
    for (const [key, label, n] of defs) {
      const div = document.createElement("div");
      div.className = "tab" + (statusFilter === key ? " active" : "");
      div.textContent = `${label} · ${n}`;
      div.addEventListener("click", () => {
        if (statusFilter === key) return;
        statusFilter = key;
        listPage = 1;
        loadList();
      });
      root.appendChild(div);
    }
  }

  function renderRow(row) {
    const api = A();
    const tr = document.createElement("tr");
    tr.dataset.id = row.id;
    const badge = statusBadge(row.status);
    const title = row.focus_ref
      ? `Ref ${row.focus_ref}`
      : `NF ${String(row.idempotency_key || row.id).slice(0, 12)}`;
    const reject =
      row.status === "rejected" && row.rejection_code
        ? `<div class="cell-sub">${escapeHtml(row.rejection_code)}</div>`
        : "";

    tr.innerHTML = `
      <td>
        <div class="cell-title">${escapeHtml(title)}</div>
        <div class="cell-sub">${escapeHtml(customerName(row.customer))}</div>
        ${reject}
      </td>
      <td>${escapeHtml(serviceName(row.service))}</td>
      <td>${escapeHtml(api.formatCompetence(row.competence_date))}</td>
      <td><span class="badge ${badge.cls}">${badge.label}</span></td>
      <td class="num">${escapeHtml(api.formatBrlFromCents(row.amount_cents))}</td>
      <td class="row-actions"></td>`;

    const actions = tr.querySelector(".row-actions");
    const st = String(row.status || "").toLowerCase();

    if (["rejected", "failed"].includes(st)) {
      actions.appendChild(
        iconBtn("Reprocessar", "reprocess", () => reprocess(row.id))
      );
    }
    if (["authorized", "draft", "pending_tax", "queued", "submitting", "polling"].includes(st)) {
      actions.appendChild(iconBtn("Cancelar", "cancel", () => openCancel(row.id)));
    }
    if (!TERMINAL.has(st)) {
      actions.appendChild(iconBtn("Atualizar status", "poll", () => pollOnce(row.id)));
    }
    return tr;
  }

  function iconBtn(title, kind, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "icon-btn";
    btn.title = title;
    btn.innerHTML =
      kind === "reprocess"
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg>'
        : kind === "cancel"
          ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>'
          : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>';
    btn.addEventListener("click", onClick);
    return btn;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function ensureIdempotency() {
    if (!nfIdempotencyKey) nfIdempotencyKey = crypto.randomUUID();
    return nfIdempotencyKey;
  }

  function resetIdempotency() {
    nfIdempotencyKey = null;
  }

  async function resolveTaxPreview() {
    const api = A();
    const form = document.getElementById("form-nfse");
    const out = document.getElementById("nf-tax-preview");
    if (!form || !out) return;
    const profileId = form.fiscal_profile_id.value;
    const serviceId = form.service_id.value;
    const providerId = form.provider_id.value;
    const ibge = resolveIbgeCode(providerId);
    const competence = form.competence_date.value;
    const service = caches.byId.services[serviceId];
    const profile = caches.byId.profiles[profileId];
    if (!profileId || !serviceId || !providerId || !competence || !service || !profile) {
      out.textContent = "Preencha prestador, perfil, serviço e competência para pré-visualizar o imposto.";
      return;
    }
    out.textContent = "Resolvendo regra fiscal…";
    try {
      const data = await api.api("/tax/resolve", {
        method: "POST",
        body: {
          fiscal_profile_id: profileId,
          ibge_code: ibge,
          service_code: service.service_code,
          tax_regime: profile.tax_regime,
          competence_date: competence,
        },
      });
      out.textContent = `Regra: ${JSON.stringify(data)}`;
    } catch (err) {
      const { message } = api.handleApiError(err.body);
      out.textContent = message;
    }
  }

  async function submitCreate(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-nfse");
    const statusEl = document.getElementById("nf-emit-status");
    api.clearFieldErrors(form);
    if (statusEl) statusEl.textContent = "";

    let amount_cents;
    try {
      amount_cents = api.reaisToCents(form.amount_reais.value);
    } catch (e) {
      api.showFieldErrors(form, { amount_reais: e.message });
      return;
    }

    if (!form.service_id.value) {
      api.showFieldErrors(form, { service_id: "Selecione um serviço da lista." });
      const search = document.getElementById("nf-service-search");
      if (search) search.focus();
      return;
    }

    const body = {
      idempotency_key: ensureIdempotency(),
      provider_id: form.provider_id.value,
      customer_id: form.customer_id.value,
      service_id: form.service_id.value,
      fiscal_profile_id: form.fiscal_profile_id.value,
      ibge_code: resolveIbgeCode(form.provider_id.value),
      competence_date: form.competence_date.value,
      amount_cents,
    };

    const submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;
    if (statusEl) {
      statusEl.innerHTML = '<span class="spinner"></span> Enviando e processando…';
    }

    try {
      const created = await api.api("/nf-issue", { method: "POST", body });
      resetIdempotency();
      api.toast("NFS-e criada. Acompanhando processamento…", "info");
      await startPolling(created.id, statusEl);
      api.closeModal("modal-nfse");
      form.reset();
      resetServiceCombo();
      await loadList();
    } catch (err) {
      const { message, fields } = api.handleApiError(err.body);
      if (Object.keys(fields).length) api.showFieldErrors(form, fields);
      else if (statusEl) statusEl.textContent = message;
      else api.toast(message, "danger");
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  async function startPolling(id, statusEl) {
    const api = A();
    const delays = [4000, 6000, 8000, 10000];
    let elapsed = 0;
    const maxMs = 60000;
    let i = 0;
    while (elapsed < maxMs) {
      const wait = delays[Math.min(i, delays.length - 1)];
      await sleep(wait);
      elapsed += wait;
      i += 1;
      try {
        const row = await api.api(`/nf-issue/${id}`);
        const badge = statusBadge(row.status);
        if (statusEl) {
          statusEl.textContent = `Status: ${badge.label}${row.rejection_code ? " — " + row.rejection_code : ""}`;
        }
        if (TERMINAL.has(String(row.status).toLowerCase())) {
          if (row.status === "authorized") api.toast("NFS-e autorizada.", "success");
          else if (row.status === "rejected")
            api.toast(`Rejeitada: ${row.rejection_code || "sem código"}`, "danger");
          else api.toast(`Status final: ${badge.label}`, "info");
          return row;
        }
      } catch (err) {
        const { message } = api.handleApiError(err.body);
        if (statusEl) statusEl.textContent = message;
      }
    }
    api.toast("Ainda em processamento. Atualize a lista depois.", "warning");
    if (statusEl) statusEl.textContent = "Ainda em processamento — atualize depois.";
    return null;
  }

  async function pollOnce(id) {
    const api = A();
    try {
      const row = await api.api(`/nf-issue/${id}`);
      api.toast(`Status: ${statusBadge(row.status).label}`, "info");
      await loadList();
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  async function reprocess(id) {
    const api = A();
    try {
      await api.api(`/nf-issue/${id}/reprocess`, { method: "POST", body: {} });
      api.toast("Reprocessamento enfileirado.", "success");
      await loadList();
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  function openCancel(id) {
    const form = document.getElementById("form-nfse-cancel");
    if (!form) return;
    form.dataset.id = id;
    form.justificativa.value = "";
    form.codigo_cancelamento.value = "";
    A().clearFieldErrors(form);
    A().openModal("modal-nfse-cancel");
  }

  async function submitCancel(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-nfse-cancel");
    api.clearFieldErrors(form);
    const justificativa = (form.justificativa.value || "").trim();
    if (justificativa.length < 15) {
      api.showFieldErrors(form, {
        justificativa: "Informe no mínimo 15 caracteres.",
      });
      return;
    }
    const body = { justificativa };
    const cod = (form.codigo_cancelamento.value || "").trim();
    if (cod) body.codigo_cancelamento = Number(cod);

    try {
      await api.api(`/nf-issue/${form.dataset.id}/cancel`, { method: "POST", body });
      api.toast("Cancelamento solicitado.", "success");
      api.closeModal("modal-nfse-cancel");
      await loadList();
    } catch (err) {
      const { message, fields } = api.handleApiError(err.body);
      if (Object.keys(fields).length) api.showFieldErrors(form, fields);
      else api.toast(message, "danger");
    }
  }

  function openCreateModal() {
    resetIdempotency();
    const form = document.getElementById("form-nfse");
    if (form) {
      form.reset();
      A().clearFieldErrors(form);
    }
    resetServiceCombo();
    const statusEl = document.getElementById("nf-emit-status");
    if (statusEl) statusEl.textContent = "";
    const preview = document.getElementById("nf-tax-preview");
    if (preview) preview.textContent = "";

    // Competência: sem min=hoje — Admin permite retroativa.
    const competence = document.getElementById("nf-competence");
    if (competence) {
      competence.removeAttribute("min");
      competence.removeAttribute("max");
      if (!competence.value) {
        competence.value = new Date().toISOString().slice(0, 10);
      }
    }

    const amount = document.getElementById("nf-amount");
    if (amount) A().bindMoneyMask(amount);

    A().openModal("modal-nfse");
    loadLookups().catch((err) => {
      A().toast(A().handleApiError(err.body).message, "danger");
    });
  }

  function bind() {
    bindServiceAutocomplete();
    const btn = document.getElementById("btn-emitir-nfse");
    if (btn) btn.addEventListener("click", openCreateModal);
    const form = document.getElementById("form-nfse");
    if (form) form.addEventListener("submit", submitCreate);
    const cancelForm = document.getElementById("form-nfse-cancel");
    if (cancelForm) cancelForm.addEventListener("submit", submitCancel);
    const taxBtn = document.getElementById("btn-nf-tax-resolve");
    if (taxBtn) taxBtn.addEventListener("click", resolveTaxPreview);
    const amount = document.getElementById("nf-amount");
    if (amount) A().bindMoneyMask(amount);
    const competence = document.getElementById("nf-competence");
    if (competence) {
      competence.removeAttribute("min");
      competence.removeAttribute("max");
    }
    const prev = document.getElementById("btn-nfse-prev");
    const next = document.getElementById("btn-nfse-next");
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
  }

  global.HubNfse = {
    bind,
    loadList,
    loadLookups,
    openCreateModal,
    renderCharts,
  };
})(window);
