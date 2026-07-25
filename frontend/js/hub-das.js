/** EXEQ Hub — tela Guias DAS (#screen-das). */
(function (global) {
  "use strict";

  const A = () => global.HubApi;

  /** @type {any[]} */
  let providers = [];
  /** @type {Record<string, any>} */
  let byProvider = {};
  let idempotencyKey = null;

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function statusBadge(status) {
    const s = String(status || "").toUpperCase();
    if (s === "DISPONIVEL" || s === "PAGO") return { cls: "success", label: s === "PAGO" ? "Pago" : "Disponível" };
    if (s === "PROCESSANDO") return { cls: "info", label: "Processando" };
    if (s === "VENCIDO" || s === "CANCELADO") return { cls: "danger", label: s === "VENCIDO" ? "Vencido" : "Cancelado" };
    if (s === "RETIFICADO") return { cls: "warning", label: "Retificado" };
    return { cls: "neutral", label: status || "—" };
  }

  function formatCompetencia(ym) {
    const m = String(ym || "").match(/^(\d{4})-(\d{2})$/);
    if (!m) return ym || "—";
    return `${m[2]}/${m[1]}`;
  }

  function formatMoney(value) {
    const n = Number(value);
    if (Number.isNaN(n)) return String(value ?? "—");
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function ensureIdempotency() {
    if (!idempotencyKey) idempotencyKey = crypto.randomUUID();
    return idempotencyKey;
  }

  function resetIdempotency() {
    idempotencyKey = null;
  }

  async function loadProviders() {
    const api = A();
    const data = await api.api("/providers");
    providers = api.unwrapList(data);
    byProvider = {};
    for (const p of providers) byProvider[p.id] = p;
    fillProviderSelect();
  }

  function fillProviderSelect() {
    const el = document.getElementById("das-provider");
    if (!el) return;
    el.innerHTML = '<option value="">Selecione…</option>';
    for (const p of providers) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.trade_name || p.legal_name || "Prestador"} — ${p.document || ""}`;
      el.appendChild(opt);
    }
  }

  function providerLabel(id) {
    const p = byProvider[id];
    if (!p) return { title: String(id || "").slice(0, 8), sub: "" };
    return {
      title: p.trade_name || p.legal_name || p.document,
      sub: p.document || "",
    };
  }

  async function loadProxyHint() {
    const el = document.getElementById("das-proxy-hint");
    if (!el) return;
    try {
      const data = await A().api("/electronic-proxies/");
      const rows = A().unwrapList(data);
      const active = rows.filter((r) =>
        ["active", "expiring"].includes(String(r.status || "").toLowerCase())
      );
      if (!active.length) {
        el.textContent =
          "Nenhuma procuração e-CAC ativa/expiring. Em RECEITA_HTTP_MODE=http a emissão exige proxy PGDASD.";
        return;
      }
      const first = active[0];
      el.textContent = `${active.length} procuração(ões) utilizável(is). Ex.: ${
        first.label || first.principal_cnpj || first.id
      } · status ${first.status}${
        first.valid_to ? ` · até ${A().formatDateBr(first.valid_to)}` : ""
      }.`;
    } catch {
      el.textContent = "Não foi possível carregar procurações e-CAC.";
    }
  }

  async function loadList() {
    const api = A();
    const tbody = document.getElementById("tbody-das");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6">Carregando…</td></tr>';
    try {
      if (!providers.length) await loadProviders();
      await loadProxyHint();
      const data = await api.api("/das/guias/");
      const rows = api.unwrapList(data);
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6">Nenhuma guia emitida.</td></tr>';
        return;
      }
      tbody.innerHTML = "";
      for (const row of rows) {
        const badge = statusBadge(row.status);
        const prov = providerLabel(row.provider);
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>
            <div class="cell-title">${escapeHtml(prov.title)}</div>
            <div class="cell-sub">${escapeHtml(prov.sub)}</div>
          </td>
          <td>${escapeHtml(formatCompetencia(row.competencia))}</td>
          <td><span class="chip">${escapeHtml(row.tipo_guia === "DAS" ? "PGDASD" : row.tipo_guia)}</span></td>
          <td><span class="badge ${badge.cls}">${badge.label}</span></td>
          <td class="num">${escapeHtml(formatMoney(row.valor_total))}</td>
          <td class="row-actions"></td>`;
        const actions = tr.querySelector(".row-actions");
        if (row.has_pdf || row.pdf_file) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "icon-btn";
          btn.title = "Baixar PDF";
          btn.innerHTML =
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 4v12M6 10l6-6 6 6" transform="rotate(180 12 10)"/><path d="M4 20h16"/></svg>';
          btn.addEventListener("click", () => downloadPdf(row));
          actions.appendChild(btn);
        }
        tbody.appendChild(tr);
      }
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="6">${escapeHtml(api.handleApiError(err.body).message)}</td></tr>`;
    }
  }

  async function downloadPdf(row) {
    const api = A();
    try {
      const blob = await api.api(`/das/guias/${row.id}/pdf/`, {
        method: "GET",
        blob: true,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `guia-${row.tipo_guia}-${row.competencia}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      api.toast(api.handleApiError(err.body).message, "danger");
    }
  }

  async function openCreate() {
    resetIdempotency();
    const form = document.getElementById("form-das");
    if (form) {
      form.reset();
      A().clearFieldErrors(form);
    }
    const st = document.getElementById("das-emit-status");
    if (st) st.textContent = "";
    try {
      await loadProviders();
      const month = document.querySelector('#form-das [name="competencia"]');
      if (month && !month.value) {
        const now = new Date();
        month.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
      }
      A().openModal("modal-das");
    } catch (err) {
      A().toast(A().handleApiError(err.body).message, "danger");
    }
  }

  async function submitCreate(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-das");
    const statusEl = document.getElementById("das-emit-status");
    api.clearFieldErrors(form);
    if (statusEl) statusEl.textContent = "";

    const body = {
      idempotency_key: ensureIdempotency(),
      provider_id: form.provider_id.value,
      tipo_guia: form.tipo_guia.value,
      competencia: form.competencia.value,
    };
    if (!body.provider_id) {
      api.showFieldErrors(form, { provider_id: "Selecione o prestador." });
      return;
    }
    if (!body.competencia) {
      api.showFieldErrors(form, { competencia: "Informe a competência." });
      return;
    }

    const btn = form.querySelector('[type="submit"]');
    if (btn) btn.disabled = true;
    if (statusEl) statusEl.textContent = "Gerando guia…";
    try {
      const created = await api.api("/das/guias/", { method: "POST", body });
      resetIdempotency();
      api.toast(`Guia ${created.tipo_guia} ${created.competencia} disponível.`, "success");
      api.closeModal("modal-das");
      await loadList();
    } catch (err) {
      const { message, fields } = api.handleApiError(err.body);
      if (Object.keys(fields).length) api.showFieldErrors(form, fields);
      else if (statusEl) statusEl.textContent = message;
      else api.toast(message, "danger");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function bind() {
    const btn = document.getElementById("btn-gerar-guia");
    if (btn) btn.addEventListener("click", openCreate);
    const form = document.getElementById("form-das");
    if (form) form.addEventListener("submit", submitCreate);
  }

  global.HubDas = { bind, loadList, openCreate };
})(window);
