/** EXEQ Hub — Painel (#screen-dashboard) com dados reais do mesmo BD do Admin. */
(function (global) {
  "use strict";

  const A = () => global.HubApi;
  const OPEN_STATUSES = ["pending", "registered", "overdue"];

  /** @type {{ total: number, by_status: Record<string, number> }} */
  let chargeSummary = { total: 0, by_status: {} };
  /** @type {{ total: number, by_status: Record<string, number> }} */
  let nfSummary = { total: 0, by_status: {} };
  /** @type {any[]} */
  let recentCharges = [];
  /** @type {Record<string, any>} */
  let byCustomer = {};
  /** @type {any[]} */
  let certificates = [];
  /** @type {{ openCount: number, openCents: number, due7Count: number, due7Cents: number }} */
  let openAgg = { openCount: 0, openCents: 0, due7Count: 0, due7Cents: 0 };

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function statusBadge(status) {
    const map = {
      pending: { cls: "warning", label: "Pendente" },
      registered: { cls: "info", label: "Registrada" },
      paid: { cls: "success", label: "Paga" },
      overdue: { cls: "danger", label: "Vencida" },
      cancelled: { cls: "neutral", label: "Cancelada" },
      failed: { cls: "danger", label: "Falhou" },
    };
    return map[String(status || "").toLowerCase()] || { cls: "neutral", label: status || "—" };
  }

  function certBadge(status) {
    const s = String(status || "").toLowerCase();
    if (s === "active") return { cls: "success", label: "Ativo" };
    if (s === "expiring") return { cls: "warning", label: "A expirar" };
    if (s === "expired") return { cls: "danger", label: "Expirado" };
    if (s === "revoked") return { cls: "neutral", label: "Revogado" };
    return { cls: "neutral", label: status || "—" };
  }

  function parseIsoDate(iso) {
    if (!iso) return null;
    const d = new Date(`${String(iso).slice(0, 10)}T12:00:00`);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function greetingName() {
    const s = A().getSession();
    if (s && s.user_name) return s.user_name;
    if (s && s.user_email) return s.user_email;
    const slug = (s && s.tenant_slug) || "";
    return slug ? `Tenant ${slug}` : "operador";
  }

  async function loadCustomers(ids) {
    const api = A();
    const need = [...new Set(ids.filter(Boolean))].filter((id) => !byCustomer[id]);
    if (!need.length) return;
    try {
      const data = await api.api("/customers/");
      for (const c of api.unwrapList(data)) {
        byCustomer[c.id] = c;
      }
    } catch {
      /* labels caem para id parcial */
    }
  }

  async function aggregateOpenCharges() {
    const api = A();
    const today = new Date();
    today.setHours(12, 0, 0, 0);
    const in7 = new Date(today);
    in7.setDate(in7.getDate() + 7);

    let openCount = 0;
    let openCents = 0;
    let due7Count = 0;
    let due7Cents = 0;

    await Promise.all(
      OPEN_STATUSES.map(async (status) => {
        try {
          const data = await api.api(
            `/charges/?status=${encodeURIComponent(status)}&page_size=100`
          );
          const page = api.unwrapPage(data);
          for (const row of page.results) {
            openCount += 1;
            openCents += Number(row.amount_cents) || 0;
            const due = parseIsoDate(row.due_date);
            if (due && due >= today && due <= in7) {
              due7Count += 1;
              due7Cents += Number(row.amount_cents) || 0;
            }
          }
        } catch {
          /* mantém zeros parciais */
        }
      })
    );

    openAgg = { openCount, openCents, due7Count, due7Cents };
  }

  function renderKpis() {
    const api = A();
    const by = chargeSummary.by_status || {};
    const nfBy = nfSummary.by_status || {};
    const nfAuthorized = nfBy.authorized || 0;
    const certExpiring = certificates.filter(
      (c) => String(c.status).toLowerCase() === "expiring"
    ).length;

    const set = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    set("dash-kpi-open-value", api.formatBrlFromCents(openAgg.openCents));
    set(
      "dash-kpi-open-delta",
      openAgg.openCount
        ? `${openAgg.openCount} cobrança(s) pendente/registrada/vencida`
        : "Nenhuma cobrança em aberto"
    );

    set("dash-kpi-due7-value", api.formatBrlFromCents(openAgg.due7Cents));
    set(
      "dash-kpi-due7-delta",
      openAgg.due7Count
        ? `${openAgg.due7Count} boleto(s) com vencimento em até 7 dias`
        : "Nenhum vencimento nos próximos 7 dias"
    );

    set("dash-kpi-nfse-value", String(nfAuthorized));
    set(
      "dash-kpi-nfse-delta",
      `Autorizadas no tenant · ${nfSummary.total || 0} nota(s) no total`
    );

    set("dash-kpi-cert-value", String(certExpiring));
    set(
      "dash-kpi-cert-delta",
      certExpiring
        ? "Certificado(s) com status a expirar"
        : "Nenhum certificado a expirar"
    );

    const chip = document.getElementById("dash-status-chip");
    if (chip) chip.textContent = `${chargeSummary.total || 0} total`;

    const head = document.getElementById("dash-greeting");
    if (head) head.textContent = `Olá, ${greetingName()}`;
  }

  function renderCharts() {
    if (!global.HubCharts) return;
    const by = chargeSummary.by_status || {};
    const col = HubCharts.palette();
    HubCharts.renderStatusBars("chartStatus", {
      labels: ["Paga", "Registrada", "Pendente", "Vencida", "Cancelada", "Falhou"],
      values: [
        by.paid || 0,
        by.registered || 0,
        by.pending || 0,
        by.overdue || 0,
        by.cancelled || 0,
        by.failed || 0,
      ],
      colors: [col.success, col.info, col.warning, col.danger, col.neutral, col.danger],
    });
  }

  function renderRecentCharges() {
    const api = A();
    const tbody = document.getElementById("tbody-dash-charges");
    const pager = document.getElementById("dash-charges-pager");
    if (!tbody) return;

    if (!recentCharges.length) {
      tbody.innerHTML =
        '<tr><td colspan="4">Nenhuma cobrança neste tenant. Crie no Admin ou em Cobranças.</td></tr>';
      if (pager) pager.textContent = "0 cobranças";
      return;
    }

    tbody.innerHTML = "";
    for (const row of recentCharges) {
      const badge = statusBadge(row.status);
      const cust = byCustomer[row.customer];
      const title = cust ? cust.name || cust.document : String(row.customer || "").slice(0, 8);
      const sub = cust ? cust.document || "" : "";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>
          <div class="cell-title">${escapeHtml(title)}</div>
          <div class="cell-sub">${escapeHtml(sub)}</div>
        </td>
        <td>${escapeHtml(api.formatDateBr(row.due_date))}</td>
        <td><span class="badge ${badge.cls}">${escapeHtml(badge.label)}</span></td>
        <td class="num">${escapeHtml(api.formatBrlFromCents(row.amount_cents))}</td>`;
      tbody.appendChild(tr);
    }
    if (pager) {
      pager.textContent = `Exibindo ${recentCharges.length} de ${
        chargeSummary.total || recentCharges.length
      } cobranças`;
    }
  }

  function renderCerts() {
    const api = A();
    const root = document.getElementById("dash-certs-list");
    if (!root) return;

    if (!certificates.length) {
      root.innerHTML =
        '<p class="hint">Nenhum certificado A1 neste tenant. Cadastre em Certificados ou no Admin.</p>';
      return;
    }

    root.innerHTML = "";
    for (const row of certificates.slice(0, 5)) {
      const badge = certBadge(row.status);
      const div = document.createElement("div");
      div.style.cssText =
        "display:flex; justify-content:space-between; align-items:center;";
      div.innerHTML = `
        <div>
          <div class="cell-title">${escapeHtml(row.label || "A1")}${
            row.is_primary ? ' <span class="chip">primary</span>' : ""
          }</div>
          <div class="cell-sub">Válido até ${escapeHtml(
            api.formatDateBr(row.not_after)
          )}</div>
        </div>
        <span class="badge ${badge.cls}">${escapeHtml(badge.label)}</span>`;
      root.appendChild(div);
    }
  }

  async function loadScreen() {
    const api = A();
    if (!api.isAuthenticated()) return;

    const emptyHint = document.getElementById("dash-empty-hint");
    if (emptyHint) emptyHint.hidden = true;

    try {
      const [chSum, nfSum, chargesPage, certs] = await Promise.all([
        api.api("/charges/summary/"),
        api.api("/nf-issue/summary/"),
        api.api("/charges/?page=1&page_size=10"),
        api.api("/certificates/"),
      ]);
      chargeSummary =
        chSum && typeof chSum === "object"
          ? { total: chSum.total || 0, by_status: chSum.by_status || {} }
          : { total: 0, by_status: {} };
      nfSummary =
        nfSum && typeof nfSum === "object"
          ? { total: nfSum.total || 0, by_status: nfSum.by_status || {} }
          : { total: 0, by_status: {} };
      recentCharges = api.unwrapPage(chargesPage).results;
      certificates = api.unwrapList(certs);
      await Promise.all([
        loadCustomers(recentCharges.map((c) => c.customer)),
        aggregateOpenCharges(),
      ]);
      renderKpis();
      renderRecentCharges();
      renderCerts();
      requestAnimationFrame(() => {
        requestAnimationFrame(() => renderCharts());
      });
      if (
        emptyHint &&
        !(chargeSummary.total || nfSummary.total || certificates.length)
      ) {
        emptyHint.hidden = false;
      }
    } catch (err) {
      const msg = api.handleApiError(err.body).message;
      api.toast(msg || "Falha ao carregar o painel.", "error");
      const tbody = document.getElementById("tbody-dash-charges");
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="4">${escapeHtml(msg)}</td></tr>`;
      }
    }
  }

  function bind() {
    const uploadBtn = document.getElementById("dash-btn-upload-cert");
    if (uploadBtn) {
      uploadBtn.addEventListener("click", () => {
        if (global.goTo) goTo("certificados");
        if (global.HubCertificates && HubCertificates.openUpload) {
          HubCertificates.openUpload();
        }
      });
    }
  }

  global.HubDashboard = { bind, loadScreen, renderCharts };
})(window);
