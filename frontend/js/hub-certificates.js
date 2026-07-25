/** EXEQ Hub — tela Certificados A1 (#screen-certificados). */
(function (global) {
  "use strict";

  const A = () => global.HubApi;

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatCnpj(digits) {
    const d = String(digits || "").replace(/\D/g, "");
    if (d.length !== 14) return digits || "—";
    return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
  }

  function statusBadge(status) {
    const s = String(status || "").toLowerCase();
    if (s === "active") return { cls: "success", label: "Ativo" };
    if (s === "expiring") return { cls: "warning", label: "A expirar" };
    if (s === "expired") return { cls: "danger", label: "Expirado" };
    if (s === "revoked") return { cls: "neutral", label: "Revogado" };
    return { cls: "neutral", label: status || "—" };
  }

  function usageLabel(usage) {
    const list = Array.isArray(usage) ? usage : [];
    if (!list.length) return "—";
    return list
      .map((u) => String(u).toUpperCase())
      .join(" · ");
  }

  function expiryPct(notAfter) {
    if (!notAfter) return 0;
    const end = new Date(notAfter).getTime();
    const now = Date.now();
    const start = end - 365 * 24 * 3600 * 1000;
    if (end <= now) return 100;
    const pct = ((now - start) / (end - start)) * 100;
    return Math.max(5, Math.min(95, Math.round(pct)));
  }

  async function loadList() {
    const api = A();
    const tbody = document.getElementById("tbody-certificados");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7">Carregando…</td></tr>';
    try {
      const data = await api.api("/certificates/");
      const rows = api.unwrapList(data);
      if (!rows.length) {
        tbody.innerHTML =
          '<tr><td colspan="7">Nenhum certificado A1 cadastrado.</td></tr>';
        return;
      }
      tbody.innerHTML = "";
      for (const row of rows) {
        const badge = statusBadge(row.status);
        const thumb = String(row.thumbprint_sha256 || "").slice(0, 8);
        const pct = expiryPct(row.not_after);
        const barColor =
          String(row.status).toLowerCase() === "expired"
            ? "var(--danger)"
            : pct > 75
              ? "var(--warning)"
              : "var(--success)";
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>
            <div class="cell-title">${escapeHtml(row.label || "A1")}${
              row.is_primary ? ' <span class="chip">primary</span>' : ""
            }</div>
            <div class="cell-sub">v${escapeHtml(row.version)} · ${escapeHtml(thumb)}…</div>
          </td>
          <td>${escapeHtml(formatCnpj(row.cnpj))}</td>
          <td><span class="chip">${escapeHtml(String(row.cert_type || "a1").toUpperCase())}</span></td>
          <td><span class="chip">${escapeHtml(usageLabel(row.key_usage))}</span></td>
          <td>
            <div class="cell-title" style="font-family:var(--font-mono); font-size:12.5px;">${escapeHtml(api.formatDateBr(row.not_after))}</div>
            <div class="expiry-bar"><span style="width:${pct}%; background:${barColor};"></span></div>
          </td>
          <td><span class="badge ${badge.cls}">${badge.label}</span></td>
          <td class="row-actions"></td>`;
        tbody.appendChild(tr);
      }
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7">${escapeHtml(api.handleApiError(err.body).message)}</td></tr>`;
    }
  }

  function openUpload() {
    const form = document.getElementById("form-cert-upload");
    if (form) {
      form.reset();
      A().clearFieldErrors(form);
    }
    const st = document.getElementById("cert-upload-status");
    if (st) st.textContent = "";
    A().openModal("modal-cert");
  }

  async function submitUpload(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-cert-upload");
    const statusEl = document.getElementById("cert-upload-status");
    api.clearFieldErrors(form);
    if (statusEl) statusEl.textContent = "";
    const file = form.file.files[0];
    if (!file) {
      api.showFieldErrors(form, { file: "Selecione o PFX/P12." });
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("label", (form.label.value || "A1").trim());
    fd.append("cnpj", (form.cnpj.value || "").trim());
    if (form.password.value) fd.append("password", form.password.value);

    const btn = form.querySelector('[type="submit"]');
    if (btn) btn.disabled = true;
    if (statusEl) statusEl.textContent = "Enviando…";
    try {
      await api.api("/certificates/upload", { method: "POST", body: fd });
      api.toast("Certificado enviado.", "success");
      api.closeModal("modal-cert");
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
    const btn = document.getElementById("btn-upload-cert");
    if (btn) btn.addEventListener("click", openUpload);
    const form = document.getElementById("form-cert-upload");
    if (form) form.addEventListener("submit", submitUpload);
  }

  global.HubCertificates = { bind, loadList, openUpload };
})(window);
