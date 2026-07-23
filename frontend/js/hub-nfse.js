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
    fillSelect("nf-service", caches.services, (s) => s.description || s.service_code);
    fillSelect("nf-profile", caches.profiles, (p) => p.name || p.id);
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

  function customerName(id) {
    const c = caches.byId.customers[id];
    return c ? c.name || c.document : String(id || "").slice(0, 8);
  }

  function serviceName(id) {
    const s = caches.byId.services[id];
    return s ? s.description || s.service_code : "—";
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
    const ibge = form.ibge_code.value.trim();
    const competence = form.competence_date.value;
    const service = caches.byId.services[serviceId];
    const profile = caches.byId.profiles[profileId];
    if (!profileId || !serviceId || !ibge || !competence || !service || !profile) {
      out.textContent = "Preencha perfil, serviço, IBGE e competência para pré-visualizar o imposto.";
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

    const body = {
      idempotency_key: ensureIdempotency(),
      provider_id: form.provider_id.value,
      customer_id: form.customer_id.value,
      service_id: form.service_id.value,
      fiscal_profile_id: form.fiscal_profile_id.value,
      ibge_code: form.ibge_code.value.trim(),
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
    const statusEl = document.getElementById("nf-emit-status");
    if (statusEl) statusEl.textContent = "";
    const preview = document.getElementById("nf-tax-preview");
    if (preview) preview.textContent = "";
    const ibge = form && form.ibge_code;
    if (ibge && !ibge.value) ibge.value = "3504107";

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
  };
})(window);
