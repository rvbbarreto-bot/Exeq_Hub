/** EXEQ Hub — bootstrap login + navegação das telas reais. */
(function (global) {
  "use strict";

  const A = () => global.HubApi;

  function showLogin(message) {
    const overlay = document.getElementById("login-overlay");
    const app = document.querySelector(".app");
    if (overlay) overlay.classList.add("is-open");
    if (app) app.classList.add("is-locked");
    const err = document.getElementById("login-error");
    if (err) err.textContent = message || "";
  }

  function hideLogin() {
    const overlay = document.getElementById("login-overlay");
    const app = document.querySelector(".app");
    if (overlay) overlay.classList.remove("is-open");
    if (app) app.classList.remove("is-locked");
    const err = document.getElementById("login-error");
    if (err) err.textContent = "";
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
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function refreshActiveScreen() {
    if (!A().isAuthenticated()) return;
    const active = document.querySelector(".screen.active");
    if (!active) return;
    if (active.id === "screen-nfse" && global.HubNfse) {
      await HubNfse.loadList();
    }
    if (active.id === "screen-cobrancas" && global.HubCharges) {
      await HubCharges.loadList();
      if (HubCharges.loadPresets) await HubCharges.loadPresets();
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
        if (ev.target === modal) modal.classList.remove("is-open");
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
    if (global.HubNfse) HubNfse.bind();
    if (global.HubCharges) HubCharges.bind();

    const loginForm = document.getElementById("form-login");
    if (loginForm) loginForm.addEventListener("submit", onLoginSubmit);

    // goTo é definido no script inline abaixo — adia o patch.
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

  global.HubApp = { showLogin, hideLogin, refreshActiveScreen, init };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
