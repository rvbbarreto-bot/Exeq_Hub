/** EXEQ Hub — tela Cobranças (#screen-cobrancas). */
(function (global) {
  "use strict";

  const A = () => global.HubApi;

  const caches = {
    customers: [],
    nfIssues: [],
    byCustomer: {},
    cancelMotivos: null,
  };

  let chargeIdempotencyKey = null;
  /** @type {any[]} */
  let pageCharges = [];
  let statusFilter = "all";
  let listPage = 1;
  const PAGE_SIZE = 20;
  /** @type {{ total: number, by_status: Record<string, number> }} */
  let summary = { total: 0, by_status: {} };
  let hasNext = false;
  let hasPrev = false;
  let pageCount = 0;

  function statusBadge(status) {
    const s = String(status || "").toLowerCase();
    if (s === "pending") return { cls: "warning", label: "Pendente" };
    if (s === "registered") return { cls: "info", label: "Registrada" };
    if (s === "paid") return { cls: "success", label: "Paga" };
    if (s === "overdue") return { cls: "danger", label: "Vencida" };
    if (s === "cancelled") return { cls: "neutral", label: "Cancelada" };
    if (s === "failed") return { cls: "danger", label: "Falhou" };
    return { cls: "neutral", label: status || "—" };
  }

  function kindLabel(kind) {
    const k = String(kind || "").toLowerCase();
    if (k === "installment") return "Parcelada";
    if (k === "recurring") return "Recorrente";
    return "Única";
  }

  function scheduleSub(row) {
    const kind = String(row.charge_kind || "simple").toLowerCase();
    if (kind === "simple") return "";
    const n = row.installment_number;
    const total = row.installment_count;
    const parts = [kindLabel(kind)];
    if (n && total) parts.push(`${n}/${total}`);
    else if (n) parts.push(`#${n}`);
    return parts.join(" · ");
  }

  function selectedChargeKind(form) {
    const checked = form.querySelector('input[name="charge_kind"]:checked');
    return (checked && checked.value) || "simple";
  }

  function syncKindFields(form) {
    if (!form) return;
    const kind = selectedChargeKind(form);
    const countField = document.getElementById("ch-field-installments");
    const endField = document.getElementById("ch-field-recurrence-end");
    const amountLabel = document.getElementById("ch-amount-label");
    const amountHint = document.getElementById("ch-amount-hint");
    const countInput = document.getElementById("ch-installment-count");
    const endInput = document.getElementById("ch-recurrence-end");

    if (countField) countField.classList.toggle("is-hidden", kind === "simple");
    if (endField) endField.classList.toggle("is-hidden", kind !== "recurring");

    if (kind === "installment") {
      if (amountLabel) amountLabel.textContent = "Valor total (R$)";
      if (amountHint) {
        amountHint.textContent =
          "Total a dividir entre as parcelas. Mínimo R$ 2,50 por parcela.";
      }
      if (countInput) {
        countInput.min = "2";
        countInput.max = "48";
        countInput.required = true;
      }
      if (endInput) {
        endInput.required = false;
        endInput.value = "";
      }
    } else if (kind === "recurring") {
      if (amountLabel) amountLabel.textContent = "Valor por ocorrência (R$)";
      if (amountHint) {
        amountHint.textContent =
          "Valor de cada boleto mensal. Informe quantidade ou data fim.";
      }
      if (countInput) {
        countInput.min = "1";
        countInput.max = "60";
        countInput.required = false;
      }
      if (endInput) endInput.required = false;
    } else {
      if (amountLabel) amountLabel.textContent = "Valor (R$)";
      if (amountHint) {
        amountHint.textContent = "Mínimo R$ 2,50. Formato automático (ex.: 6,00).";
      }
      if (countInput) {
        countInput.required = false;
        countInput.value = "";
      }
      if (endInput) {
        endInput.required = false;
        endInput.value = "";
      }
    }
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function ensureIdempotency() {
    if (!chargeIdempotencyKey) chargeIdempotencyKey = crypto.randomUUID();
    return chargeIdempotencyKey;
  }

  function resetIdempotency() {
    chargeIdempotencyKey = null;
  }

  async function loadLookups() {
    const api = A();
    const [customers, nfIssues] = await Promise.all([
      api.api("/customers"),
      api.api("/nf-issue/?status=authorized&page_size=100"),
    ]);
    caches.customers = api.unwrapList(customers);
    caches.byCustomer = {};
    for (const c of caches.customers) caches.byCustomer[c.id] = c;

    caches.nfIssues = api.unwrapList(nfIssues);

    fillCustomerSelect();
    fillNfSelect();
  }

  function fillCustomerSelect() {
    const el = document.getElementById("ch-customer");
    if (!el) return;
    el.innerHTML = '<option value="">Selecione…</option>';
    for (const c of caches.customers) {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.name || "Cliente"} — ${c.document || ""}`;
      el.appendChild(opt);
    }
  }

  function fillNfSelect() {
    const el = document.getElementById("ch-nf-issue");
    if (!el) return;
    el.innerHTML = '<option value="">(opcional) Sem vínculo</option>';
    for (const n of caches.nfIssues) {
      const cust = caches.byCustomer[n.customer];
      const opt = document.createElement("option");
      opt.value = n.id;
      opt.textContent = `${n.focus_ref || n.idempotency_key} — ${cust ? cust.name : ""} — ${A().formatBrlFromCents(n.amount_cents)}`;
      el.appendChild(opt);
    }
  }

  function customerLabel(id) {
    const c = caches.byCustomer[id];
    if (!c) return { title: String(id || "").slice(0, 8), sub: "" };
    return { title: c.name || c.document, sub: c.document || "" };
  }

  async function loadSummary() {
    try {
      summary = await A().api("/charges/summary/");
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
    const tbody = document.getElementById("tbody-cobrancas");
    const pager = document.getElementById("pager-cobrancas-label");
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
      const data = await api.api(`/charges/?${params.toString()}`);
      const page = api.unwrapPage(data);
      pageCharges = page.results;
      pageCount = page.count;
      hasNext = Boolean(page.next);
      hasPrev = Boolean(page.previous);
      renderTabs();
      renderTable();
      updatePagerLabel();
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="6">${escapeHtml(api.handleApiError(err.body).message)}</td></tr>`;
    }
  }

  function updatePagerLabel() {
    const pager = document.getElementById("pager-cobrancas-label");
    const prev = document.getElementById("btn-cobrancas-prev");
    const next = document.getElementById("btn-cobrancas-next");
    const from = pageCount === 0 ? 0 : (listPage - 1) * PAGE_SIZE + 1;
    const to = Math.min(listPage * PAGE_SIZE, pageCount);
    if (pager) {
      pager.textContent =
        pageCount === 0
          ? "Nenhuma cobrança"
          : `Exibindo ${from}–${to} de ${pageCount}`;
    }
    if (prev) prev.disabled = !hasPrev;
    if (next) next.disabled = !hasNext;
  }

  function renderTabs() {
    const root = document.getElementById("tabs-cobrancas");
    if (!root) return;
    const by = summary.by_status || {};
    const defs = [
      ["all", "Todas", summary.total || 0],
      ["pending", "Pendentes", by.pending || 0],
      ["registered", "Registradas", by.registered || 0],
      ["paid", "Pagas", by.paid || 0],
      ["overdue", "Vencidas", by.overdue || 0],
      ["cancelled", "Canceladas", by.cancelled || 0],
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

  function renderTable() {
    const tbody = document.getElementById("tbody-cobrancas");
    if (!tbody) return;
    const rows = pageCharges;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6">Nenhuma cobrança neste filtro.</td></tr>';
      return;
    }
    tbody.innerHTML = "";
    for (const row of rows) {
      tbody.appendChild(renderRow(row));
    }
  }

  function renderRow(row) {
    const api = A();
    const tr = document.createElement("tr");
    tr.dataset.id = row.id;
    const badge = statusBadge(row.status);
    const cust = customerLabel(row.customer);
    const sched = scheduleSub(row);
    const descSub = sched
      ? `<div class="cell-sub">${escapeHtml(sched)}</div>`
      : "";
    tr.innerHTML = `
      <td>
        <div class="cell-title">${escapeHtml(cust.title)}</div>
        <div class="cell-sub">${escapeHtml(cust.sub)}</div>
      </td>
      <td>
        <div class="cell-title">${escapeHtml(row.description || "—")}</div>
        ${descSub}
      </td>
      <td>${escapeHtml(api.formatDateBr(row.due_date))}</td>
      <td><span class="badge ${badge.cls}">${badge.label}</span></td>
      <td class="num">${escapeHtml(api.formatBrlFromCents(row.amount_cents))}</td>
      <td class="row-actions"></td>`;

    const actions = tr.querySelector(".row-actions");
    actions.appendChild(
      iconBtn("Detalhes", "detail", () => openDetails(row))
    );
    if (row.gateway_ref) {
      actions.appendChild(
        iconBtn("Sincronizar gateway", "sync", () => syncCharge(row.id))
      );
    }
    if (row.has_boleto_pdf || row.boleto_pdf_url || row.payment_url) {
      actions.appendChild(
        iconBtn("Baixar boleto PDF", "download", () => downloadPdf(row))
      );
    }
    const st = String(row.status).toLowerCase();
    if (["pending", "registered", "overdue"].includes(st)) {
      actions.appendChild(
        iconBtn("Cancelar", "cancel", () => cancelCharge(row.id))
      );
    }
    return tr;
  }

  function iconBtn(title, kind, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "icon-btn";
    btn.title = title;
    const svgs = {
      download:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 4v12M6 10l6-6 6 6" transform="rotate(180 12 10)"/><path d="M4 20h16"/></svg>',
      cancel:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>',
      detail:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>',
      sync:
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg>',
    };
    btn.innerHTML = svgs[kind] || svgs.detail;
    btn.addEventListener("click", onClick);
    return btn;
  }

  function openDetails(row) {
    const api = A();
    const body = document.getElementById("charge-detail-body");
    if (!body) return;
    const badge = statusBadge(row.status);
    const needsSync = row.gateway_ref && !(row.digitable_line || row.pix_copy_paste);
    const kind = String(row.charge_kind || "simple").toLowerCase();
    const frac =
      kind !== "simple" && row.installment_number && row.installment_count
        ? ` · ${row.installment_number}/${row.installment_count}`
        : "";
    body.innerHTML = `
      <div class="detail-grid">
        <div><span class="muted">Status</span><div><span class="badge ${badge.cls}">${badge.label}</span></div></div>
        <div><span class="muted">Tipo</span><div>${escapeHtml(kindLabel(row.charge_kind) + frac)}</div></div>
        <div><span class="muted">Valor</span><div class="mono">${escapeHtml(api.formatBrlFromCents(row.amount_cents))}</div></div>
        <div><span class="muted">Vencimento</span><div>${escapeHtml(api.formatDateBr(row.due_date))}</div></div>
        <div><span class="muted">Gateway ref</span><div class="mono">${escapeHtml(row.gateway_ref || "—")}</div></div>
        <div><span class="muted">Código de controle</span><div class="mono">${escapeHtml(row.seu_numero || "—")}</div></div>
        ${
          row.schedule_group_id
            ? `<div class="full"><span class="muted">Grupo do carnê</span><div class="mono">${escapeHtml(row.schedule_group_id)}</div></div>`
            : ""
        }
        <div class="full"><span class="muted">Linha digitável</span>
          <div class="copy-row"><code>${escapeHtml(row.digitable_line || "—")}</code>
          ${row.digitable_line ? '<button type="button" class="btn btn-ghost btn-sm" data-copy="digitable">Copiar</button>' : ""}</div>
        </div>
        <div class="full"><span class="muted">Código de barras</span><div class="mono">${escapeHtml(row.barcode || "—")}</div></div>
        <div class="full"><span class="muted">PIX copia e cola</span>
          <div class="copy-row"><code class="pix">${escapeHtml(row.pix_copy_paste || "—")}</code>
          ${row.pix_copy_paste ? '<button type="button" class="btn btn-ghost btn-sm" data-copy="pix">Copiar código PIX</button>' : ""}</div>
        </div>
        <div class="full detail-actions">
          ${row.payment_url ? `<a class="btn btn-primary btn-sm" href="${escapeHtml(row.payment_url)}" target="_blank" rel="noopener">Ver cobrança</a>` : ""}
          ${
            row.has_boleto_pdf || row.boleto_pdf_url || row.gateway_ref
              ? `<button type="button" class="btn btn-ghost btn-sm" id="btn-detail-pdf">Baixar boleto PDF</button>`
              : ""
          }
          ${row.gateway_ref ? `<button type="button" class="btn btn-ghost btn-sm" id="btn-detail-sync">Sincronizar</button>` : ""}
        </div>
        ${needsSync ? '<div class="full hint">Artefatos ainda vazios — use Sincronizar para buscar linha digitável/PIX no gateway.</div>' : ""}
      </div>`;
    body.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.getAttribute("data-copy");
        api.copyText(kind === "pix" ? row.pix_copy_paste : row.digitable_line);
      });
    });
    const pdfBtn = document.getElementById("btn-detail-pdf");
    if (pdfBtn) {
      pdfBtn.addEventListener("click", () => downloadPdf(row));
    }
    const syncBtn = document.getElementById("btn-detail-sync");
    if (syncBtn) {
      syncBtn.addEventListener("click", async () => {
        const updated = await syncCharge(row.id, { reopenDetails: true });
        if (updated) openDetails(updated);
      });
    }
    api.openModal("modal-charge-detail");
  }

  async function syncCharge(id, opts) {
    const api = A();
    const options = opts || {};
    try {
      const updated = await api.api(`/charges/${id}/sync`, { method: "POST", body: {} });
      api.toast("Cobrança sincronizada.", "success");
      await loadList();
      if (options.reopenDetails) return updated;
      return updated;
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
      return null;
    }
  }

  async function downloadPdf(row) {
    const api = A();
    if (row.boleto_pdf_url && !row.has_boleto_pdf) {
      window.open(row.boleto_pdf_url, "_blank");
      return;
    }
    if (!row.id) return;
    try {
      const blob = await api.api(`/charges/${row.id}/pdf`, { method: "GET", blob: true });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `boleto-${row.seu_numero || row.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  async function ensureCancelMotivos() {
    if (caches.cancelMotivos) return caches.cancelMotivos;
    const data = await A().api("/billing/cancel-motivos");
    caches.cancelMotivos = data;
    return data;
  }

  async function openCancelModal(id) {
    const api = A();
    const form = document.getElementById("form-charge-cancel");
    const select = document.getElementById("ch-cancel-motivo");
    const statusEl = document.getElementById("ch-cancel-status");
    if (!form || !select) return;
    api.clearFieldErrors(form);
    if (statusEl) statusEl.textContent = "";
    form.charge_id.value = id;
    try {
      const data = await ensureCancelMotivos();
      select.innerHTML = (data.motivos || [])
        .map(
          (m) =>
            `<option value="${escapeHtml(m.value)}"${
              m.value === data.default ? " selected" : ""
            }>${escapeHtml(m.label)}</option>`
        )
        .join("");
      api.openModal("modal-charge-cancel");
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  async function submitCancel(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-charge-cancel");
    const statusEl = document.getElementById("ch-cancel-status");
    api.clearFieldErrors(form);
    if (statusEl) statusEl.textContent = "";
    const id = form.charge_id.value;
    const motivo = form.motivo_cancelamento.value;
    if (!id || !motivo) {
      api.showFieldErrors(form, { motivo_cancelamento: "Selecione o motivo." });
      return;
    }
    const submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;
    try {
      await api.api(`/charges/${id}/cancel`, {
        method: "POST",
        body: { motivo_cancelamento: motivo },
      });
      api.toast("Cobrança cancelada.", "success");
      api.closeModal("modal-charge-cancel");
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

  function cancelCharge(id) {
    openCancelModal(id);
  }

  async function enrichIfNeeded(charge) {
    if (!charge || !charge.id) return charge;
    if (charge.digitable_line || charge.pix_copy_paste) return charge;
    if (!charge.gateway_ref) return charge;
    try {
      return await A().api(`/charges/${charge.id}/sync`, { method: "POST", body: {} });
    } catch {
      return charge;
    }
  }

  async function submitCreate(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-charge");
    const statusEl = document.getElementById("ch-emit-status");
    api.clearFieldErrors(form);
    if (statusEl) statusEl.textContent = "";

    let amount_cents;
    try {
      amount_cents = api.reaisToCents(form.amount_reais.value);
    } catch (e) {
      api.showFieldErrors(form, { amount_reais: e.message });
      return;
    }
    if (amount_cents < 250) {
      api.showFieldErrors(form, { amount_reais: "Valor mínimo da cobrança é R$ 2,50." });
      return;
    }

    const minDue = api.minDueDateIso();
    if (!form.due_date.value || form.due_date.value < minDue) {
      api.showFieldErrors(form, {
        due_date: `Vencimento mínimo: ${api.formatDateBr(minDue)}.`,
      });
      return;
    }

    const charge_kind = selectedChargeKind(form);
    const body = {
      idempotency_key: ensureIdempotency(),
      customer_id: form.customer_id.value,
      amount_cents,
      due_date: form.due_date.value,
      description: (form.description.value || "").trim(),
      charge_kind,
    };

    if (charge_kind === "installment") {
      const count = Number(form.installment_count.value || 0);
      if (!Number.isInteger(count) || count < 2 || count > 48) {
        api.showFieldErrors(form, {
          installment_count: "Informe entre 2 e 48 parcelas.",
        });
        return;
      }
      if (Math.floor(amount_cents / count) < 250) {
        api.showFieldErrors(form, {
          amount_reais: "Cada parcela deve ter no mínimo R$ 2,50.",
        });
        return;
      }
      body.installment_count = count;
    } else if (charge_kind === "recurring") {
      const countRaw = (form.installment_count.value || "").trim();
      const end = (form.recurrence_end_date.value || "").trim();
      if (!countRaw && !end) {
        api.showFieldErrors(form, {
          installment_count: "Informe quantidade ou data fim da recorrência.",
          recurrence_end_date: "Informe quantidade ou data fim da recorrência.",
        });
        return;
      }
      if (countRaw) {
        const count = Number(countRaw);
        if (!Number.isInteger(count) || count < 1 || count > 60) {
          api.showFieldErrors(form, {
            installment_count: "Quantidade deve estar entre 1 e 60.",
          });
          return;
        }
        body.installment_count = count;
      }
      if (end) {
        if (end < form.due_date.value) {
          api.showFieldErrors(form, {
            recurrence_end_date: "Data fim deve ser ≥ ao 1º vencimento.",
          });
          return;
        }
        body.recurrence_end_date = end;
      }
    }

    const seu = (form.seu_numero && form.seu_numero.value || "").trim();
    if (seu) {
      if (seu.length > 15) {
        api.showFieldErrors(form, {
          seu_numero: "Código de controle deve ter no máximo 15 caracteres.",
        });
        return;
      }
      body.seu_numero = seu;
    }
    if (form.nf_issue_id.value) body.nf_issue_id = form.nf_issue_id.value;

    const submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;
    if (statusEl) {
      statusEl.textContent =
        charge_kind === "simple"
          ? "Emitindo boleto…"
          : "Emitindo carnê no gateway…";
    }

    try {
      const created = await api.api("/charges", { method: "POST", body });
      let charges = [];
      if (created && Array.isArray(created.charges)) {
        charges = created.charges;
      } else if (Array.isArray(created)) {
        charges = created;
      } else if (created) {
        charges = [created];
      }
      if (!charges.length) {
        throw { body: { detail: "Resposta de emissão vazia." } };
      }

      let first = charges[0];
      first = await enrichIfNeeded(first);
      resetIdempotency();
      const n = charges.length;
      api.toast(
        n > 1
          ? `${n} cobranças emitidas (${kindLabel(charge_kind)}).`
          : first.digitable_line || first.pix_copy_paste
            ? "Cobrança emitida com artefatos."
            : "Cobrança emitida. Sincronize se a linha ainda estiver vazia.",
        "success"
      );
      api.closeModal("modal-charge");
      form.reset();
      syncKindFields(form);
      listPage = 1;
      await loadList();
      openDetails(first);
    } catch (err) {
      const { message, fields } = api.handleApiError(err.body);
      if (err.body && err.body.gateway) {
        if (statusEl) statusEl.textContent = String(err.body.gateway);
        else api.toast(String(err.body.gateway), "danger");
      } else if (Object.keys(fields).length) {
        api.showFieldErrors(form, fields);
        if (statusEl && message) statusEl.textContent = message;
      } else if (statusEl) statusEl.textContent = message;
      else api.toast(message, "danger");
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  function openCreateModal() {
    resetIdempotency();
    const form = document.getElementById("form-charge");
    if (form) {
      form.reset();
      A().clearFieldErrors(form);
      const simple = form.querySelector('input[name="charge_kind"][value="simple"]');
      if (simple) simple.checked = true;
      syncKindFields(form);
    }
    const statusEl = document.getElementById("ch-emit-status");
    if (statusEl) statusEl.textContent = "";
    const amount = document.getElementById("ch-amount");
    if (amount) A().bindMoneyMask(amount);
    A().applyDueDateConstraints(document.getElementById("ch-due-date"));
    A().openModal("modal-charge");
    loadLookups().catch((err) => {
      A().toast(A().handleApiError(err.body).message, "danger");
    });
  }

  function fillPresetForm(preset) {
    const form = document.getElementById("form-billing-presets");
    if (!form || !preset) return;
    form.num_dias_agenda.value = preset.num_dias_agenda ?? 0;
    form.apply_multa.checked = Boolean(preset.apply_multa);
    form.multa_percent.value = String(preset.multa_percent || "0").replace(".", ",");
    form.apply_mora.checked = Boolean(preset.apply_mora);
    form.mora_percent_am.value = String(preset.mora_percent_am || "0").replace(".", ",");
  }

  async function loadPresets() {
    const api = A();
    try {
      const preset = await api.api("/billing/presets");
      fillPresetForm(preset);
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  async function submitPresets(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-billing-presets");
    if (!form) return;
    api.clearFieldErrors(form);
    const body = {
      num_dias_agenda: Number(form.num_dias_agenda.value || 0),
      apply_multa: Boolean(form.apply_multa.checked),
      multa_percent: String(form.multa_percent.value || "0").replace(",", "."),
      apply_mora: Boolean(form.apply_mora.checked),
      mora_percent_am: String(form.mora_percent_am.value || "0").replace(",", "."),
    };
    const submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;
    try {
      const saved = await api.api("/billing/presets", { method: "PUT", body });
      fillPresetForm(saved);
      api.toast("Predefinições salvas.", "success");
    } catch (err) {
      const { message, fields } = api.handleApiError(err.body);
      if (Object.keys(fields).length) api.showFieldErrors(form, fields);
      else api.toast(message, "danger");
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  function bind() {
    document.querySelectorAll(".js-nova-cobranca").forEach((btn) => {
      btn.addEventListener("click", openCreateModal);
    });
    const form = document.getElementById("form-charge");
    if (form) {
      form.addEventListener("submit", submitCreate);
      form.querySelectorAll('input[name="charge_kind"]').forEach((el) => {
        el.addEventListener("change", () => syncKindFields(form));
      });
      syncKindFields(form);
    }
    const cancelForm = document.getElementById("form-charge-cancel");
    if (cancelForm) cancelForm.addEventListener("submit", submitCancel);
    const presetForm = document.getElementById("form-billing-presets");
    if (presetForm) presetForm.addEventListener("submit", submitPresets);
    const amount = document.getElementById("ch-amount");
    if (amount) A().bindMoneyMask(amount);
    A().applyDueDateConstraints(document.getElementById("ch-due-date"));
    const prev = document.getElementById("btn-cobrancas-prev");
    const next = document.getElementById("btn-cobrancas-next");
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

  global.HubCharges = {
    bind,
    loadList,
    loadLookups,
    loadPresets,
    openCreateModal,
    syncCharge,
  };
})(window);
