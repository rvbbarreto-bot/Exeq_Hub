/** EXEQ Hub — bootstrap login + navegação das telas reais. */
(function (global) {
  "use strict";

  const A = () => global.HubApi;

  function initialsFromName(name, email) {
    const raw = String(name || "").trim();
    if (raw) {
      const parts = raw.split(/\s+/).filter(Boolean);
      if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
      }
      return raw.slice(0, 2).toUpperCase();
    }
    const em = String(email || "").trim();
    return em ? em.slice(0, 2).toUpperCase() : "—";
  }

  function refreshSessionChrome() {
    const s = A().getSession();
    const brand = document.getElementById("hub-brand-tenant");
    const pill = document.getElementById("hub-tenant-pill");
    const avatar = document.getElementById("hub-user-avatar");
    const nameEl = document.getElementById("hub-user-name");
    const metaEl = document.getElementById("hub-user-meta");

    if (!s || !s.access) {
      if (brand) brand.textContent = "—";
      if (pill) pill.textContent = "—";
      if (avatar) avatar.textContent = "—";
      if (nameEl) nameEl.textContent = "Não autenticado";
      if (metaEl) metaEl.textContent = "Faça login";
      return;
    }

    const tenantLabel = s.tenant_legal_name || s.tenant_slug || "—";
    const shortTenant =
      s.tenant_slug ||
      (tenantLabel.length > 28 ? `${tenantLabel.slice(0, 28)}…` : tenantLabel);
    if (brand) brand.textContent = shortTenant;
    if (pill) pill.textContent = tenantLabel;
    if (avatar) avatar.textContent = initialsFromName(s.user_name, s.user_email);
    if (nameEl) nameEl.textContent = s.user_name || s.user_email || "Usuário";
    if (metaEl) {
      metaEl.textContent = `${s.role_code || "—"} · ${shortTenant}`;
    }
  }

  function showLogin(message) {
    const overlay = document.getElementById("login-overlay");
    const app = document.querySelector(".app");
    if (overlay) overlay.classList.add("is-open");
    if (app) app.classList.add("is-locked");
    const err = document.getElementById("login-error");
    if (err) err.textContent = message || "";
    refreshSessionChrome();
  }

  function hideLogin() {
    const overlay = document.getElementById("login-overlay");
    const app = document.querySelector(".app");
    if (overlay) overlay.classList.remove("is-open");
    if (app) app.classList.remove("is-locked");
    const err = document.getElementById("login-error");
    if (err) err.textContent = "";
    refreshSessionChrome();
  }

  async function onLoginSubmit(ev) {
    ev.preventDefault();
    const api = A();
    const form = document.getElementById("form-login");
    const err = document.getElementById("login-error");
    if (err) err.textContent = "";
    const btn = form.querySelector('[type="submit"]');
    if (btn) btn.disabled = true;
    try {
      await api.login({
        tenant_slug: form.tenant_slug.value.trim(),
        email: form.email.value.trim(),
        password: form.password.value,
      });
      hideLogin();
      api.toast("Sessão iniciada.", "success");
      await refreshActiveScreen();
    } catch (e) {
      const { message } = api.handleApiError(e.body);
      if (err) err.textContent = message || "Falha no login.";
      refreshSessionChrome();
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function refreshActiveScreen() {
    if (!A().isAuthenticated()) return;
    refreshSessionChrome();
    const active = document.querySelector(".screen.active");
    if (!active) return;
    if (active.id === "screen-dashboard" && global.HubDashboard) {
      await HubDashboard.loadScreen();
    }
    if (active.id === "screen-nfse" && global.HubNfse) {
      await HubNfse.loadList();
    }
    if (active.id === "screen-cobrancas" && global.HubCharges) {
      await HubCharges.loadList();
      if (HubCharges.loadPresets) await HubCharges.loadPresets();
    }
    if (active.id === "screen-provedor" && global.HubProvider) {
      await HubProvider.loadScreen();
    }
    if (active.id === "screen-certificados" && global.HubCertificates) {
      await HubCertificates.loadList();
    }
    if (active.id === "screen-das" && global.HubDas) {
      await HubDas.loadList();
    }
  }

  function patchGoTo() {
    const original = global.goTo;
    if (typeof original !== "function") return;
    global.goTo = function (name) {
      original(name);
      if (!A().isAuthenticated()) {
        showLogin();
        return;
      }
      refreshActiveScreen().catch(() => {});
    };
  }

  function bindModals() {
    document.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-close-modal");
        if (id) A().closeModal(id);
      });
    });
    document.querySelectorAll(".hub-modal").forEach((modal) => {
      modal.addEventListener("click", (ev) => {
        if (ev.target === modal) A().closeModal(modal.id);
      });
    });
  }

  function bindLogout() {
    const btn = document.getElementById("btn-logout");
    if (!btn) return;
    btn.addEventListener("click", () => {
      A().clearSession();
      showLogin("Sessão encerrada.");
    });
  }

  function init() {
    bindModals();
    bindLogout();
    refreshSessionChrome();
    if (global.HubDashboard) HubDashboard.bind();
    if (global.HubNfse) HubNfse.bind();
    if (global.HubCharges) HubCharges.bind();
    if (global.HubProvider) HubProvider.bind();
    if (global.HubCertificates) HubCertificates.bind();
    if (global.HubDas) HubDas.bind();

    const loginForm = document.getElementById("form-login");
    if (loginForm) loginForm.addEventListener("submit", onLoginSubmit);

    setTimeout(() => {
      patchGoTo();
      if (!A().isAuthenticated()) {
        showLogin();
      } else {
        hideLogin();
        refreshActiveScreen().catch(() => {});
      }
    }, 0);
  }

  global.HubApp = {
    showLogin,
    hideLogin,
    refreshActiveScreen,
    refreshSessionChrome,
    init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
