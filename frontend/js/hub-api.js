/** EXEQ Hub — cliente API (JWT em memória, refresh, erros). */
(function (global) {
  "use strict";

  const API_BASE = "/api/v1";

  /** Endpoints registrados sem trailing slash em config/urls (não-router). */
  const NO_SLASH_PATHS = new Set([
    "/auth/login",
    "/auth/refresh",
    "/tax/resolve",
    "/certificates/upload",
    "/integrations/focus/token",
    "/integrations/focus/empresas",
    "/billing/provider",
    "/billing/presets",
    "/billing/cancel-motivos",
    "/billing/providers/inter/credentials",
    "/billing/providers/inter/test-connection",
    "/billing/providers/inter/webhook",
    "/billing/providers/inter/webhook/callbacks/retry",
    "/webhooks/gateway",
    "/webhooks/focus-nfse",
    "/openapi.json",
  ]);

  /**
   * DRF DefaultRouter exige barra final; paths explícitos do urls.py em geral não.
   * Evita RuntimeError APPEND_SLASH em POST/PUT/PATCH.
   */
  function normalizeApiPath(path) {
    let p = String(path || "");
    const qIndex = p.indexOf("?");
    let query = "";
    if (qIndex >= 0) {
      query = p.slice(qIndex);
      p = p.slice(0, qIndex);
    }
    if (!p.startsWith("/")) p = `/${p}`;
    p = p.replace(/\/{2,}/g, "/");
    const bare = p.replace(/\/$/, "") || "/";
    if (NO_SLASH_PATHS.has(bare) || bare.startsWith("/integrations/focus/municipios/")) {
      return bare + query;
    }
    if (bare.startsWith("/billing/providers/") && bare.endsWith("/credentials")) {
      return bare + query;
    }
    if (!p.endsWith("/")) p += "/";
    return p + query;
  }

  /** @type {{ access: string, refresh: string, tenant_slug: string, role_code: string } | null} */
  let session = null;

  const ERROR_CODES = {
    incompatible_payment: "Operação incompatível com o status atual do pagamento.",
    charge_not_found: "Cobrança não encontrada.",
    invalid_transition: "Transição de status não permitida para esta nota.",
    gateway: "Falha ao comunicar com o gateway de cobrança.",
    authentication_failed: "Sessão expirada. Faça login novamente.",
    min_amount: "Valor abaixo do mínimo permitido.",
  };

  function setSession(data) {
    session = data
      ? {
          access: data.access,
          refresh: data.refresh,
          tenant_slug: data.tenant_slug || "",
          role_code: data.role_code || "",
        }
      : null;
  }

  function getSession() {
    return session;
  }

  function isAuthenticated() {
    return Boolean(session && session.access);
  }

  function clearSession() {
    session = null;
  }

  function unwrapList(data) {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.results)) return data.results;
    return [];
  }

  /** DRF PageNumberPagination ou lista crua. */
  function unwrapPage(data) {
    if (Array.isArray(data)) {
      return {
        results: data,
        count: data.length,
        next: null,
        previous: null,
      };
    }
    if (data && typeof data === "object") {
      const results = Array.isArray(data.results) ? data.results : [];
      return {
        results,
        count: Number(data.count != null ? data.count : results.length) || 0,
        next: data.next || null,
        previous: data.previous || null,
      };
    }
    return { results: [], count: 0, next: null, previous: null };
  }

  /**
   * @param {any} body
   * @param {{ fieldEls?: Record<string, HTMLElement|null> }=} opts
   * @returns {{ message: string, fields: Record<string, string> }}
   */
  function handleApiError(body, opts) {
    const fields = {};
    let message = "Não foi possível concluir a operação.";

    if (!body || typeof body !== "object") {
      return { message, fields };
    }

    if (body.code && ERROR_CODES[body.code]) {
      message = ERROR_CODES[body.code];
    } else if (typeof body.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      message = body.detail.map((d) => (typeof d === "string" ? d : d.msg || JSON.stringify(d))).join("; ");
    } else if (body.gateway) {
      message = typeof body.gateway === "string" ? body.gateway : String(body.gateway);
    }

    for (const [key, val] of Object.entries(body)) {
      if (key === "detail" || key === "code" || key === "gateway") continue;
      if (Array.isArray(val)) {
        fields[key] = val.map(String).join(" ");
      } else if (typeof val === "string") {
        fields[key] = val;
      } else if (val != null) {
        fields[key] = String(val);
      }
    }

    if (opts && opts.fieldEls) {
      for (const [key, el] of Object.entries(opts.fieldEls)) {
        if (!el) continue;
        const errEl = el.parentElement && el.parentElement.querySelector(".field-error");
        if (errEl) errEl.textContent = fields[key] || "";
      }
    }

    return { message, fields };
  }

  function reaisToCents(raw) {
    let text = String(raw || "").trim().replace(/R\$\s?/gi, "").replace(/\s/g, "");
    if (!text) throw new Error("Informe o valor.");
    if (text.includes(".") && text.includes(",")) {
      text = text.replace(/\./g, "").replace(",", ".");
    } else if (text.includes(",")) {
      text = text.replace(",", ".");
    }
    const n = Number(text);
    if (!Number.isFinite(n) || n <= 0) throw new Error("Valor inválido.");
    return Math.round(n * 100);
  }

  /** Formata digitação como 1.234,56 (sem prefixo R$). */
  function formatBrlInputFromDigits(raw) {
    const digits = String(raw || "").replace(/\D/g, "");
    if (!digits) return "";
    const cents = parseInt(digits, 10);
    if (!Number.isFinite(cents)) return "";
    return (cents / 100).toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function formatBrlInputFromCents(cents) {
    return formatBrlFromCents(cents).replace(/^R\$\s?/, "");
  }

  /**
   * Máscara monetária BRL ao digitar (como Admin valor_reais).
   * Ex.: 1232 → 12,32 → … → 1.232,00
   */
  function bindMoneyMask(input) {
    if (!input || input.dataset.moneyMaskBound === "1") return;
    input.dataset.moneyMaskBound = "1";
    input.setAttribute("inputmode", "decimal");
    input.setAttribute("autocomplete", "off");
    input.addEventListener("input", () => {
      input.value = formatBrlInputFromDigits(input.value);
    });
    input.addEventListener("blur", () => {
      const raw = (input.value || "").trim();
      if (!raw) return;
      try {
        input.value = formatBrlInputFromCents(reaisToCents(raw));
      } catch {
        /* mantém o digitado; validação no submit */
      }
    });
  }

  function formatBrlFromCents(cents) {
    if (cents == null || cents === "") return "—";
    const n = Number(cents) / 100;
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function formatDateBr(iso) {
    if (!iso) return "—";
    const d = String(iso).slice(0, 10);
    const [y, m, day] = d.split("-");
    if (!y || !m || !day) return iso;
    return `${day}/${m}/${y}`;
  }

  function formatCompetence(iso) {
    if (!iso) return "—";
    const d = String(iso).slice(0, 10);
    const [y, m] = d.split("-");
    return `${m}/${y}`;
  }

  /** Espelha apps/billing/due_date_rules.min_due_date (corte 16:00 local). */
  function minDueDateIso(now) {
    const current = now instanceof Date ? now : new Date();
    const d = new Date(
      current.getFullYear(),
      current.getMonth(),
      current.getDate()
    );
    if (current.getHours() >= 16) {
      d.setDate(d.getDate() + 1);
    }
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function applyDueDateConstraints(input) {
    if (!input) return;
    const min = minDueDateIso();
    input.min = min;
    if (!input.value || input.value < min) input.value = min;
  }

  async function refreshAccess() {
    if (!session || !session.refresh) throw new Error("Sem refresh token");
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh: session.refresh }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      clearSession();
      throw Object.assign(new Error("Refresh falhou"), { status: res.status, body: data });
    }
    session.access = data.access;
    if (data.refresh) session.refresh = data.refresh;
    return session.access;
  }

  /**
   * @param {string} path
   * @param {{ method?: string, body?: any, headers?: Record<string,string>, _retried?: boolean, blob?: boolean }=} options
   */
  async function api(path, options) {
    const opts = options || {};
    const method = (opts.method || "GET").toUpperCase();
    const headers = {
      Accept: opts.blob ? "application/pdf" : "application/json",
      ...(opts.headers || {}),
    };
    if (session && session.access) {
      headers.Authorization = `Bearer ${session.access}`;
    }
    let body = opts.body;
    if (body != null && typeof body !== "string") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    const res = await fetch(`${API_BASE}${normalizeApiPath(path)}`, {
      method,
      headers,
      body: method === "GET" || method === "HEAD" ? undefined : body,
    });

    if (res.status === 401 && !opts._retried && session && session.refresh) {
      try {
        await refreshAccess();
        return api(path, { ...opts, _retried: true });
      } catch (e) {
        clearSession();
        if (typeof global.HubApp !== "undefined" && HubApp.showLogin) {
          HubApp.showLogin("Sessão expirada. Entre novamente.");
        }
        throw e;
      }
    }

    if (opts.blob) {
      if (!res.ok) {
        const text = await res.text();
        let data = null;
        try {
          data = text ? JSON.parse(text) : null;
        } catch {
          data = { detail: text };
        }
        const err = new Error((data && data.detail) || `HTTP ${res.status}`);
        err.status = res.status;
        err.body = data;
        throw err;
      }
      return res.blob();
    }

    const text = await res.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { detail: text };
      }
    }

    if (!res.ok) {
      const err = new Error((data && data.detail) || `HTTP ${res.status}`);
      err.status = res.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  async function login({ tenant_slug, email, password }) {
    const data = await api("/auth/login", {
      method: "POST",
      body: { tenant_slug, email, password },
      _retried: true,
    });
    setSession(data);
    return data;
  }

  function toast(message, tone) {
    let el = document.getElementById("hub-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "hub-toast";
      el.className = "hub-toast";
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.dataset.tone = tone || "info";
    el.classList.add("is-visible");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove("is-visible"), 4500);
  }

  function clearFieldErrors(form) {
    if (!form) return;
    form.querySelectorAll(".field-error").forEach((el) => {
      el.textContent = "";
    });
  }

  function showFieldErrors(form, fields) {
    if (!form || !fields) return;
    for (const [key, msg] of Object.entries(fields)) {
      const input = form.querySelector(`[name="${key}"]`);
      if (!input) continue;
      const box = input.closest(".field");
      const err = box && box.querySelector(".field-error");
      if (err) err.textContent = msg;
    }
  }

  function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add("is-open");
  }

  function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove("is-open");
  }

  async function copyText(text) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast("Copiado.", "success");
    } catch {
      toast("Não foi possível copiar.", "danger");
    }
  }

  global.HubApi = {
    API_BASE,
    setSession,
    getSession,
    isAuthenticated,
    clearSession,
    unwrapList,
    unwrapPage,
    handleApiError,
    reaisToCents,
    formatBrlInputFromDigits,
    formatBrlInputFromCents,
    bindMoneyMask,
    formatBrlFromCents,
    formatDateBr,
    formatCompetence,
    minDueDateIso,
    applyDueDateConstraints,
    api,
    login,
    toast,
    clearFieldErrors,
    showFieldErrors,
    openModal,
    closeModal,
    copyText,
    ERROR_CODES,
  };
})(window);
