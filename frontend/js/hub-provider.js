/** EXEQ Hub — tela Provedor de cobrança (#screen-provedor). */
(function (global) {
  "use strict";

  const A = () => global.HubApi;
  const PROVIDERS = [
    {
      id: "inter",
      name: "Banco Inter",
      desc: "Cobrança BolePix v3 · OAuth2 + mTLS",
    },
    {
      id: "asaas",
      name: "Asaas",
      desc: "Cobrança via token de API",
    },
    {
      id: "c6",
      name: "C6 Bank",
      desc: "Token de API (estudo — stub)",
    },
  ];

  /** @type {{ provider?: string, providers?: Record<string, {configured:boolean}> } | null} */
  let statusCache = null;
  /** @type {string} */
  let selected = "inter";

  function isAdmin() {
    const s = A().getSession();
    return (s && s.role_code) === "tenant_admin";
  }

  function setAdminGates() {
    const admin = isAdmin();
    document.querySelectorAll("[data-admin-only]").forEach((el) => {
      el.disabled = !admin;
      if (!admin) el.setAttribute("title", "Somente tenant_admin");
      else el.removeAttribute("title");
    });
    const note = document.getElementById("prov-admin-note");
    if (note) {
      note.textContent = admin
        ? ""
        : "Você pode visualizar o status. Alterar provedor/credenciais exige papel tenant_admin.";
      note.hidden = admin;
    }
  }

  function badgeFor(kind, active, configured) {
    if (kind === active) {
      return configured
        ? { cls: "success", label: "Ativo" }
        : { cls: "warning", label: "Ativo · incompleto" };
    }
    return configured
      ? { cls: "info", label: "Configurado" }
      : { cls: "neutral", label: "Não configurado" };
  }

  function renderCards() {
    const root = document.getElementById("prov-cards");
    if (!root) return;
    const active = (statusCache && statusCache.provider) || "inter";
    const providers = (statusCache && statusCache.providers) || {};
    root.innerHTML = "";
    for (const p of PROVIDERS) {
      const configured = Boolean(providers[p.id] && providers[p.id].configured);
      const badge = badgeFor(p.id, active, configured);
      const card = document.createElement("div");
      card.className =
        "provider-card" + (selected === p.id ? " selected" : "");
      card.dataset.provider = p.id;
      card.innerHTML = `
        <div class="p-check">${
          selected === p.id
            ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6 9 17l-5-5"/></svg>'
            : ""
        }</div>
        <div class="p-name">${p.name}</div>
        <div class="p-desc">${p.desc}</div>
        <span class="badge ${badge.cls}">${badge.label}</span>
        ${
          active === p.id
            ? ""
            : `<button type="button" class="btn btn-ghost btn-sm prov-activate" data-admin-only style="margin-top:10px">Definir como ativo</button>`
        }
      `;
      card.addEventListener("click", (ev) => {
        if (ev.target.closest(".prov-activate")) return;
        selected = p.id;
        renderCards();
        showPanels();
      });
      const act = card.querySelector(".prov-activate");
      if (act) {
        act.addEventListener("click", async (ev) => {
          ev.stopPropagation();
          await activateProvider(p.id);
        });
      }
      root.appendChild(card);
    }
    setAdminGates();
  }

  function showPanels() {
    document.querySelectorAll("[data-prov-panel]").forEach((el) => {
      el.hidden = el.getAttribute("data-prov-panel") !== selected;
    });
  }

  async function loadStatus() {
    statusCache = await A().api("/billing/provider");
    selected = (statusCache && statusCache.provider) || selected || "inter";
    renderCards();
    showPanels();
    setAdminGates();
  }

  async function loadInterMeta() {
    const meta = await A().api("/billing/providers/inter/credentials");
    const el = document.getElementById("prov-inter-meta");
    if (!el) return;
    el.textContent = [
      `Client ID: ${meta.client_id_masked || "—"}`,
      `Secret: ${meta.has_client_secret ? "definido" : "ausente"}`,
      `Cert: ${meta.has_cert ? "sim" : "não"}`,
      `Key: ${meta.has_key ? "sim" : "não"}`,
      `Conta: ${meta.conta_corrente_masked || "—"}`,
      `Configurado: ${meta.configured ? "sim" : "não"}`,
    ].join(" · ");
  }

  async function loadTokenMeta(provider) {
    const meta = await A().api(`/billing/providers/${provider}/credentials`);
    const el = document.getElementById(`prov-${provider}-meta`);
    if (!el) return;
    el.textContent = `Token: ${meta.api_token_masked || "—"} · ${
      meta.configured ? "configurado" : "não configurado"
    }`;
  }

  async function activateProvider(kind) {
    if (!isAdmin()) {
      A().toast("Somente tenant_admin pode alterar o provedor.", "danger");
      return;
    }
    try {
      statusCache = await A().api("/billing/provider", {
        method: "PUT",
        body: { provider: kind },
      });
      selected = kind;
      A().toast(`Provedor ativo: ${kind}.`, "success");
      renderCards();
      showPanels();
    } catch (err) {
      A().toast(A().handleApiError(err.body).message, "danger");
    }
  }

  function setConnStatus(ok, detail) {
    const box = document.getElementById("prov-inter-conn");
    if (!box) return;
    box.classList.toggle("is-error", !ok);
    const t1 = box.querySelector(".t1");
    const t2 = box.querySelector(".t2");
    if (t1) t1.textContent = ok ? "Conexão validada" : "Falha na conexão";
    if (t2) t2.textContent = detail || "";
  }

  async function submitInter(ev) {
    ev.preventDefault();
    if (!isAdmin()) return;
    const form = document.getElementById("form-prov-inter");
    A().clearFieldErrors(form);
    const fd = new FormData(form);
    const cert = form.cert_file.files[0];
    const key = form.key_file.files[0];
    if (!cert || !key) {
      A().showFieldErrors(form, {
        cert_file: !cert ? "Obrigatório." : "",
        key_file: !key ? "Obrigatório." : "",
      });
      return;
    }
    const btn = form.querySelector('[type="submit"]');
    if (btn) btn.disabled = true;
    try {
      await A().api("/billing/providers/inter/credentials", {
        method: "POST",
        body: fd,
      });
      A().toast("Credenciais Inter salvas.", "success");
      form.reset();
      updateDropzoneLabels();
      await loadInterMeta();
      await loadStatus();
    } catch (err) {
      const { message, fields } = A().handleApiError(err.body);
      if (Object.keys(fields).length) A().showFieldErrors(form, fields);
      else A().toast(message, "danger");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function testInter() {
    if (!isAdmin()) return;
    const btn = document.getElementById("btn-prov-test-inter");
    if (btn) btn.disabled = true;
    try {
      const out = await A().api("/billing/providers/inter/test-connection", {
        method: "POST",
        body: {},
      });
      setConnStatus(true, "Handshake OAuth + mTLS OK");
      A().toast(out.status === "ok" ? "Conexão Inter OK." : "Teste concluído.", "success");
    } catch (err) {
      const { message } = A().handleApiError(err.body);
      setConnStatus(false, message);
      A().toast(message, "danger");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function submitToken(provider, formId) {
    if (!isAdmin()) return;
    const form = document.getElementById(formId);
    A().clearFieldErrors(form);
    const token = (form.api_token.value || "").trim();
    if (!token) {
      A().showFieldErrors(form, { api_token: "Informe o token." });
      return;
    }
    const btn = form.querySelector('[type="submit"]');
    if (btn) btn.disabled = true;
    try {
      await A().api(`/billing/providers/${provider}/credentials`, {
        method: "POST",
        body: { api_token: token },
      });
      A().toast(`Credenciais ${provider} salvas.`, "success");
      form.reset();
      await loadTokenMeta(provider);
      await loadStatus();
    } catch (err) {
      const { message, fields } = A().handleApiError(err.body);
      if (Object.keys(fields).length) A().showFieldErrors(form, fields);
      else A().toast(message, "danger");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function updateDropzoneLabels() {
    const cert = document.getElementById("prov-inter-cert");
    const key = document.getElementById("prov-inter-key");
    const certDz = document.getElementById("dz-inter-cert");
    const keyDz = document.getElementById("dz-inter-key");
    if (certDz) {
      const title = certDz.querySelector(".dz-title");
      if (title) {
        title.textContent = cert && cert.files[0]
          ? cert.files[0].name
          : "Selecionar certificado (.crt/.pem)";
      }
      certDz.classList.toggle("filled", Boolean(cert && cert.files[0]));
    }
    if (keyDz) {
      const title = keyDz.querySelector(".dz-title");
      if (title) {
        title.textContent = key && key.files[0]
          ? key.files[0].name
          : "Selecionar chave (.key/.pem)";
      }
      keyDz.classList.toggle("filled", Boolean(key && key.files[0]));
    }
  }

  async function loadScreen() {
    setAdminGates();
    try {
      await loadStatus();
      await Promise.all([
        loadInterMeta().catch(() => {}),
        loadTokenMeta("asaas").catch(() => {}),
        loadTokenMeta("c6").catch(() => {}),
      ]);
      setConnStatus(false, "Ainda não testado nesta sessão.");
    } catch (err) {
      A().toast(A().handleApiError(err.body).message, "danger");
    }
  }

  function bind() {
    const interForm = document.getElementById("form-prov-inter");
    if (interForm) interForm.addEventListener("submit", submitInter);
    const asaasForm = document.getElementById("form-prov-asaas");
    if (asaasForm) {
      asaasForm.addEventListener("submit", (ev) => {
        ev.preventDefault();
        submitToken("asaas", "form-prov-asaas");
      });
    }
    const c6Form = document.getElementById("form-prov-c6");
    if (c6Form) {
      c6Form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        submitToken("c6", "form-prov-c6");
      });
    }
    const testBtn = document.getElementById("btn-prov-test-inter");
    if (testBtn) testBtn.addEventListener("click", testInter);
    ["prov-inter-cert", "prov-inter-key"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("change", updateDropzoneLabels);
    });
    document.querySelectorAll("[data-dz-for]").forEach((dz) => {
      dz.addEventListener("click", () => {
        const input = document.getElementById(dz.getAttribute("data-dz-for"));
        if (input) input.click();
      });
    });
  }

  global.HubProvider = { bind, loadScreen };
})(window);
