/** EXEQ Hub — Prestadores e Tomadores (#screen-prestadores / #screen-tomadores). */
(function (global) {
  "use strict";

  const A = () => global.HubApi;
  const WRITE_ROLES = new Set(["tenant_admin", "operator"]);

  /** @type {Record<string, object>} */
  let providerById = {};
  /** @type {Record<string, object>} */
  let customerById = {};

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function canWrite() {
    const role = (A().getSession() || {}).role_code || "";
    return WRITE_ROLES.has(role);
  }

  function applyWriterUi() {
    const write = canWrite();
    document.querySelectorAll(".js-writer-only").forEach((el) => {
      el.hidden = !write;
      if (el.tagName === "BUTTON" || el.tagName === "INPUT") {
        el.disabled = !write;
      }
    });
  }

  function digits(value) {
    return String(value || "").replace(/\D/g, "");
  }

  function formatCnpj(raw) {
    const d = digits(raw);
    if (d.length !== 14) return raw || "—";
    return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
  }

  function formatCpf(raw) {
    const d = digits(raw);
    if (d.length !== 11) return raw || "—";
    return d.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, "$1.$2.$3-$4");
  }

  function sourceChip(source) {
    if (source === "receita_federal") {
      return '<span class="badge success">Receita</span>';
    }
    return '<span class="badge neutral">Manual</span>';
  }

  function setBanner(id, kind, text) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `lookup-banner is-visible ${kind}`;
    el.textContent = text;
  }

  function fillAddress(form, addr) {
    const a = addr || {};
    for (const key of [
      "logradouro",
      "numero",
      "complemento",
      "bairro",
      "cep",
      "municipio",
      "uf",
      "codigo_municipio_ibge",
    ]) {
      const input = form.querySelector(`[name="${key}"]`);
      if (input) input.value = a[key] || "";
    }
    const tel = form.querySelector('[name="telefone_receita"]');
    if (tel) tel.value = a.telefone || "";
    const em = form.querySelector('[name="email_receita"]');
    if (em) em.value = a.email || "";
  }

  function readAddress(form) {
    const get = (n) => (form.querySelector(`[name="${n}"]`)?.value || "").trim();
    return {
      logradouro: get("logradouro"),
      numero: get("numero"),
      complemento: get("complemento"),
      bairro: get("bairro"),
      cep: digits(get("cep")).slice(0, 8),
      municipio: get("municipio"),
      uf: get("uf").toUpperCase().slice(0, 2),
      codigo_municipio_ibge: get("codigo_municipio_ibge"),
      telefone: get("telefone_receita"),
      email: get("email_receita"),
    };
  }

  function applyLookupToForm(form, data, nameField) {
    const set = (n, v) => {
      const el = form.querySelector(`[name="${n}"]`);
      if (el) el.value = v == null ? "" : String(v);
    };
    set(nameField, data.legal_name || "");
    if (nameField === "legal_name") set("trade_name", data.trade_name || "");
    set("situacao_cadastral", data.situacao_cadastral || "");
    set("data_abertura", data.data_abertura || "");
    set("natureza_juridica", data.natureza_juridica || "");
    set("cnae_principal", data.cnae_principal || "");
    set("porte", data.porte || "");
    set("telefone_receita", data.telefone || "");
    set("email_receita", data.email || "");
    if (data.email && form.querySelector('[name="email"]')) {
      set("email", data.email);
    }
    fillAddress(form, data.address || {});
    set("data_source", "receita_federal");
    set("receita_raw_payload", JSON.stringify(data.raw || {}));
  }

  async function lookupDocument({ kind, form, bannerId, force, persist }) {
    if (!canWrite()) {
      A().toast("Seu papel não permite consultar/alterar cadastros.", "danger");
      return;
    }
    const doc = digits(form.querySelector('[name="document"]')?.value);
    const docType = form.querySelector('[name="document_type"]')?.value;
    if (docType === "cpf") {
      setBanner(
        bannerId,
        "info",
        "CPF: apenas validação de dígito. Preencha nome e endereço manualmente (LGPD)."
      );
      return;
    }
    if (doc.length !== 14) {
      setBanner(bannerId, "warn", "Informe um CNPJ com 14 dígitos.");
      return;
    }
    setBanner(bannerId, "info", "Consultando base cadastral…");
    const path =
      kind === "provider"
        ? "/master-data/providers/lookup-document"
        : "/master-data/customers/lookup-document";
    try {
      const data = await A().api(path, {
        method: "POST",
        body: { document: doc, force: !!force, persist: !!persist },
      });
      applyLookupToForm(form, data, kind === "provider" ? "legal_name" : "name");
      const extras = [];
      if (data.optante_simples === true) extras.push("indicador Simples Nacional");
      if (data.optante_mei === true) extras.push("indicador MEI");
      const cacheNote = data.cached ? " (cache local < 24h)" : "";
      setBanner(
        bannerId,
        "ok",
        `Dado localizado e pronto para uso${cacheNote}${
          extras.length ? " · " + extras.join(", ") : ""
        }. Revise e salve.`
      );
    } catch (err) {
      const { message } = A().handleApiError(err.body);
      setBanner(
        bannerId,
        "warn",
        message || "Consulta indisponível. Continue com preenchimento manual."
      );
    }
  }

  async function loadProviders() {
    applyWriterUi();
    const tbody = document.getElementById("tbody-prestadores");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5">Carregando…</td></tr>';
    try {
      const data = await A().api("/providers/");
      const rows = A().unwrapList(data);
      providerById = {};
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5">Nenhum prestador neste tenant.</td></tr>';
        return;
      }
      tbody.innerHTML = "";
      for (const row of rows) {
        providerById[row.id] = row;
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="mono">${escapeHtml(formatCnpj(row.document))}</td>
          <td>
            <div class="cell-title">${escapeHtml(row.legal_name)}</div>
            <div class="cell-sub">${escapeHtml(row.trade_name || "")}</div>
          </td>
          <td>${escapeHtml(row.tax_regime || "—")}</td>
          <td>${sourceChip(row.data_source)}</td>
          <td class="row-actions">
            <button type="button" class="btn btn-ghost btn-sm" data-edit-provider="${escapeHtml(row.id)}">
              ${canWrite() ? "Editar" : "Ver"}
            </button>
          </td>`;
        tbody.appendChild(tr);
      }
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="5">${escapeHtml(
        A().handleApiError(err.body).message
      )}</td></tr>`;
    }
  }

  async function loadCustomers() {
    applyWriterUi();
    const tbody = document.getElementById("tbody-tomadores");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="5">Carregando…</td></tr>';
    try {
      const data = await A().api("/customers/");
      const rows = A().unwrapList(data);
      customerById = {};
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5">Nenhum tomador neste tenant.</td></tr>';
        return;
      }
      tbody.innerHTML = "";
      for (const row of rows) {
        customerById[row.id] = row;
        const docLabel =
          row.document_type === "cpf"
            ? formatCpf(row.document)
            : formatCnpj(row.document);
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="mono">${escapeHtml(docLabel)}</td>
          <td>${escapeHtml((row.document_type || "").toUpperCase())}</td>
          <td>${escapeHtml(row.name)}</td>
          <td>${sourceChip(row.data_source)}</td>
          <td class="row-actions">
            <button type="button" class="btn btn-ghost btn-sm" data-edit-customer="${escapeHtml(row.id)}">
              ${canWrite() ? "Editar" : "Ver"}
            </button>
          </td>`;
        tbody.appendChild(tr);
      }
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="5">${escapeHtml(
        A().handleApiError(err.body).message
      )}</td></tr>`;
    }
  }

  function resetProviderForm() {
    const form = document.getElementById("form-prestador");
    if (!form) return;
    form.reset();
    form.querySelector('[name="id"]').value = "";
    form.querySelector('[name="data_source"]').value = "manual";
    form.querySelector('[name="receita_raw_payload"]').value = "";
    A().clearFieldErrors(form);
    document.getElementById("modal-prestador-title").textContent = "Novo prestador";
    document.getElementById("btn-prestador-refresh").hidden = true;
    setBanner(
      "prestador-lookup-banner",
      "info",
      "Informe um CNPJ e consulte a Receita para pré-preencher."
    );
  }

  function openProvider(row) {
    const form = document.getElementById("form-prestador");
    if (!form) return;
    resetProviderForm();
    applyWriterUi();
    if (row) {
      document.getElementById("modal-prestador-title").textContent = canWrite()
        ? "Editar prestador"
        : "Prestador";
      form.querySelector('[name="id"]').value = row.id || "";
      form.querySelector('[name="document"]').value = row.document || "";
      form.querySelector('[name="legal_name"]').value = row.legal_name || "";
      form.querySelector('[name="trade_name"]').value = row.trade_name || "";
      form.querySelector('[name="situacao_cadastral"]').value =
        row.situacao_cadastral || "";
      form.querySelector('[name="data_abertura"]').value = row.data_abertura || "";
      form.querySelector('[name="natureza_juridica"]').value =
        row.natureza_juridica || "";
      form.querySelector('[name="cnae_principal"]').value = row.cnae_principal || "";
      form.querySelector('[name="porte"]').value = row.porte || "";
      form.querySelector('[name="whatsapp"]').value = row.whatsapp || "";
      form.querySelector('[name="contato_nome"]').value = row.contato_nome || "";
      form.querySelector('[name="municipal_registration"]').value =
        row.municipal_registration || "";
      form.querySelector('[name="tax_regime"]').value =
        row.tax_regime || "simples_nacional";
      form.querySelector('[name="data_source"]').value = row.data_source || "manual";
      form.querySelector('[name="receita_raw_payload"]').value = row.receita_raw_payload
        ? JSON.stringify(row.receita_raw_payload)
        : "";
      fillAddress(form, row.address || {});
      document.getElementById("btn-prestador-refresh").hidden = !canWrite();
    }
    A().openModal("modal-prestador");
  }

  function cpfDv(base) {
    function calc(digs, weightStart) {
      let total = 0;
      for (let i = 0; i < digs.length; i += 1) {
        total += Number(digs[i]) * (weightStart - i);
      }
      const rem = total % 11;
      return rem < 2 ? "0" : String(11 - rem);
    }
    const d1 = calc(base, 10);
    const d2 = calc(base + d1, 11);
    return d1 + d2;
  }

  function isValidCpf(value) {
    const d = digits(value);
    if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
    return d.slice(9) === cpfDv(d.slice(0, 9));
  }

  function validateTomadorCpf() {
    const form = document.getElementById("form-tomador");
    if (!form) return false;
    const raw = form.querySelector('[name="document"]')?.value;
    const d = digits(raw);
    if (d.length !== 11) {
      setBanner("tomador-lookup-banner", "warn", "Informe um CPF com 11 dígitos.");
      return false;
    }
    if (!isValidCpf(d)) {
      setBanner(
        "tomador-lookup-banner",
        "warn",
        "CPF inválido (dígito verificador). Corrija antes de salvar."
      );
      return false;
    }
    setBanner(
      "tomador-lookup-banner",
      "ok",
      "CPF com dígito verificador válido. Preencha nome e endereço manualmente — a Receita não libera cadastro de CPF a terceiros (LGPD)."
    );
    return true;
  }

  function validateTomadorAddress(form) {
    const required = [
      ["cep", "CEP"],
      ["logradouro", "Logradouro"],
      ["numero", "Número"],
      ["bairro", "Bairro"],
      ["municipio", "Município"],
      ["uf", "UF"],
      ["codigo_municipio_ibge", "IBGE"],
    ];
    const missing = [];
    for (const [name, label] of required) {
      const el = form.querySelector(`[name="${name}"]`);
      const val = name === "cep" ? digits(el?.value) : (el?.value || "").trim();
      if (!val || (name === "cep" && val.length !== 8) || (name === "uf" && val.length !== 2)) {
        missing.push(label);
        if (el) {
          const box = el.closest(".field");
          const err = box && box.querySelector(".field-error");
          if (err) err.textContent = "Obrigatório";
        }
      }
    }
    return missing;
  }

  async function lookupTomadorCep({ forceBanner } = {}) {
    const form = document.getElementById("form-tomador");
    if (!form || !canWrite()) return;
    const cepInput = form.querySelector('[name="cep"]');
    const cep = digits(cepInput?.value);
    if (cep.length !== 8) {
      if (forceBanner) {
        setBanner("tomador-lookup-banner", "warn", "Informe um CEP com 8 dígitos.");
      }
      return;
    }
    setBanner("tomador-lookup-banner", "info", "Consultando CEP…");
    try {
      const data = await A().api("/master-data/lookup-cep", {
        method: "POST",
        body: { cep },
      });
      form.querySelector('[name="cep"]').value = data.cep || cep;
      form.querySelector('[name="logradouro"]').value = data.logradouro || "";
      form.querySelector('[name="bairro"]').value = data.bairro || "";
      form.querySelector('[name="municipio"]').value = data.municipio || "";
      form.querySelector('[name="uf"]').value = data.uf || "";
      form.querySelector('[name="codigo_municipio_ibge"]').value =
        data.codigo_municipio_ibge || "";
      setBanner(
        "tomador-lookup-banner",
        "ok",
        "CEP localizado. Confira o endereço e informe o número (obrigatório)."
      );
      form.querySelector('[name="numero"]')?.focus();
    } catch (err) {
      const { message } = A().handleApiError(err.body);
      setBanner(
        "tomador-lookup-banner",
        "warn",
        message || "CEP não encontrado. Preencha o endereço manualmente."
      );
    }
  }

  function toggleTomadorCnpjFields() {
    const form = document.getElementById("form-tomador");
    const type = form?.querySelector('[name="document_type"]')?.value;
    const isCpf = type === "cpf";
    document.querySelectorAll(".js-tomador-cnpj-only").forEach((el) => {
      el.hidden = isCpf;
    });
    document.querySelectorAll(".js-tomador-cpf-only").forEach((el) => {
      el.hidden = !isCpf;
    });
    // CPF: nome/endereço manuais (sem cadeado). CNPJ: campos de Receita com cadeado.
    document.querySelectorAll(".js-tomador-receita-field").forEach((el) => {
      el.classList.toggle("is-locked", !isCpf);
    });
    if (isCpf) {
      setBanner(
        "tomador-lookup-banner",
        "info",
        "Pessoa física (CPF): use Validar CPF. Não há consulta cadastral na Receita (LGPD) — preencha nome e endereço manualmente."
      );
      form.querySelector('[name="data_source"]').value = "manual";
      document.getElementById("btn-tomador-refresh").hidden = true;
    } else {
      setBanner(
        "tomador-lookup-banner",
        "info",
        "Informe um CNPJ e consulte a Receita para pré-preencher."
      );
    }
  }

  function resetCustomerForm() {
    const form = document.getElementById("form-tomador");
    if (!form) return;
    form.reset();
    form.querySelector('[name="id"]').value = "";
    form.querySelector('[name="data_source"]').value = "manual";
    form.querySelector('[name="receita_raw_payload"]').value = "";
    form.querySelector('[name="document_type"]').value = "cnpj";
    A().clearFieldErrors(form);
    document.getElementById("modal-tomador-title").textContent = "Novo tomador";
    document.getElementById("btn-tomador-refresh").hidden = true;
    toggleTomadorCnpjFields();
  }

  function openCustomer(row) {
    const form = document.getElementById("form-tomador");
    if (!form) return;
    resetCustomerForm();
    applyWriterUi();
    if (row) {
      document.getElementById("modal-tomador-title").textContent = canWrite()
        ? "Editar tomador"
        : "Tomador";
      form.querySelector('[name="id"]').value = row.id || "";
      form.querySelector('[name="document_type"]').value = row.document_type || "cnpj";
      form.querySelector('[name="document"]').value = row.document || "";
      form.querySelector('[name="name"]').value = row.name || "";
      form.querySelector('[name="email"]').value = row.email || "";
      form.querySelector('[name="situacao_cadastral"]').value =
        row.situacao_cadastral || "";
      form.querySelector('[name="data_abertura"]').value = row.data_abertura || "";
      form.querySelector('[name="natureza_juridica"]').value =
        row.natureza_juridica || "";
      form.querySelector('[name="cnae_principal"]').value = row.cnae_principal || "";
      form.querySelector('[name="porte"]').value = row.porte || "";
      form.querySelector('[name="whatsapp"]').value = row.whatsapp || "";
      form.querySelector('[name="contato_nome"]').value = row.contato_nome || "";
      form.querySelector('[name="data_source"]').value = row.data_source || "manual";
      form.querySelector('[name="receita_raw_payload"]').value = row.receita_raw_payload
        ? JSON.stringify(row.receita_raw_payload)
        : "";
      fillAddress(form, row.address || {});
      document.getElementById("btn-tomador-refresh").hidden =
        !canWrite() || row.document_type === "cpf";
      toggleTomadorCnpjFields();
    }
    A().openModal("modal-tomador");
  }

  function parseRawPayload(raw) {
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async function saveProvider(ev) {
    ev.preventDefault();
    if (!canWrite()) {
      A().toast("Seu papel não permite gravar prestadores.", "danger");
      return;
    }
    const form = ev.target;
    A().clearFieldErrors(form);
    const id = form.querySelector('[name="id"]').value;
    const payload = {
      document: digits(form.document.value),
      legal_name: form.legal_name.value.trim(),
      trade_name: form.trade_name.value.trim(),
      municipal_registration: form.municipal_registration.value.trim(),
      tax_regime: form.tax_regime.value,
      situacao_cadastral: form.situacao_cadastral.value.trim(),
      data_abertura: form.data_abertura.value || null,
      cnae_principal: form.cnae_principal.value.trim(),
      natureza_juridica: form.natureza_juridica.value.trim(),
      porte: form.porte.value.trim(),
      whatsapp: form.whatsapp.value.trim(),
      contato_nome: form.contato_nome.value.trim(),
      data_source: form.data_source.value || "manual",
      receita_raw_payload: parseRawPayload(form.receita_raw_payload.value),
      address: readAddress(form),
      is_active: true,
    };
    try {
      if (id) {
        await A().api(`/providers/${id}/`, { method: "PATCH", body: payload });
        A().toast("Prestador atualizado.", "success");
      } else {
        await A().api("/providers/", { method: "POST", body: payload });
        A().toast("Prestador cadastrado.", "success");
      }
      A().closeModal("modal-prestador");
      await loadProviders();
    } catch (err) {
      const { message, fields } = A().handleApiError(err.body);
      A().showFieldErrors(form, fields);
      A().toast(message, "danger");
    }
  }

  async function saveCustomer(ev) {
    ev.preventDefault();
    if (!canWrite()) {
      A().toast("Seu papel não permite gravar tomadores.", "danger");
      return;
    }
    const form = ev.target;
    A().clearFieldErrors(form);
    const id = form.querySelector('[name="id"]').value;
    const documentType = form.document_type.value;
    if (documentType === "cpf" && !isValidCpf(form.document.value)) {
      A().toast("CPF inválido. Corrija o dígito verificador.", "danger");
      validateTomadorCpf();
      return;
    }
    const missingAddr = validateTomadorAddress(form);
    if (missingAddr.length) {
      A().toast(
        `Preencha os campos obrigatórios: ${missingAddr.join(", ")}.`,
        "danger"
      );
      return;
    }
    const payload = {
      document: digits(form.document.value),
      document_type: documentType,
      name: form.name.value.trim(),
      email: form.email.value.trim(),
      situacao_cadastral: form.situacao_cadastral.value.trim(),
      data_abertura: form.data_abertura.value || null,
      cnae_principal: form.cnae_principal.value.trim(),
      natureza_juridica: form.natureza_juridica.value.trim(),
      porte: form.porte.value.trim(),
      whatsapp: form.whatsapp.value.trim(),
      contato_nome: form.contato_nome.value.trim(),
      data_source:
        documentType === "cpf" ? "manual" : form.data_source.value || "manual",
      receita_raw_payload:
        documentType === "cpf"
          ? null
          : parseRawPayload(form.receita_raw_payload.value),
      address: readAddress(form),
      is_active: true,
    };
    try {
      if (id) {
        await A().api(`/customers/${id}/`, { method: "PATCH", body: payload });
        A().toast("Tomador atualizado.", "success");
      } else {
        await A().api("/customers/", { method: "POST", body: payload });
        A().toast("Tomador cadastrado.", "success");
      }
      A().closeModal("modal-tomador");
      await loadCustomers();
    } catch (err) {
      const { message, fields } = A().handleApiError(err.body);
      A().showFieldErrors(form, fields);
      A().toast(message, "danger");
    }
  }

  function bind() {
    document.getElementById("btn-novo-prestador")?.addEventListener("click", () => {
      if (!canWrite()) {
        A().toast("Seu papel não permite criar prestadores.", "danger");
        return;
      }
      openProvider(null);
    });
    document.getElementById("btn-novo-tomador")?.addEventListener("click", () => {
      if (!canWrite()) {
        A().toast("Seu papel não permite criar tomadores.", "danger");
        return;
      }
      openCustomer(null);
    });

    document.getElementById("tbody-prestadores")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-edit-provider]");
      if (!btn) return;
      openProvider(providerById[btn.getAttribute("data-edit-provider")]);
    });
    document.getElementById("tbody-tomadores")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-edit-customer]");
      if (!btn) return;
      openCustomer(customerById[btn.getAttribute("data-edit-customer")]);
    });

    document.getElementById("form-prestador")?.addEventListener("submit", saveProvider);
    document.getElementById("form-tomador")?.addEventListener("submit", saveCustomer);

    document.getElementById("btn-prestador-lookup")?.addEventListener("click", () => {
      const form = document.getElementById("form-prestador");
      const id = form.querySelector('[name="id"]').value;
      lookupDocument({
        kind: "provider",
        form,
        bannerId: "prestador-lookup-banner",
        force: false,
        persist: !!id,
      });
    });
    document.getElementById("btn-prestador-refresh")?.addEventListener("click", () => {
      const form = document.getElementById("form-prestador");
      lookupDocument({
        kind: "provider",
        form,
        bannerId: "prestador-lookup-banner",
        force: true,
        persist: true,
      });
    });
    document.getElementById("btn-tomador-lookup")?.addEventListener("click", () => {
      const form = document.getElementById("form-tomador");
      const id = form.querySelector('[name="id"]').value;
      lookupDocument({
        kind: "customer",
        form,
        bannerId: "tomador-lookup-banner",
        force: false,
        persist: !!id,
      });
    });
    document.getElementById("btn-tomador-refresh")?.addEventListener("click", () => {
      const form = document.getElementById("form-tomador");
      lookupDocument({
        kind: "customer",
        form,
        bannerId: "tomador-lookup-banner",
        force: true,
        persist: true,
      });
    });
    document
      .getElementById("btn-tomador-validate-cpf")
      ?.addEventListener("click", () => {
        validateTomadorCpf();
      });
    document
      .getElementById("btn-tomador-lookup-cep")
      ?.addEventListener("click", () => lookupTomadorCep({ forceBanner: true }));
    document
      .querySelector("#form-tomador [name='cep']")
      ?.addEventListener("blur", () => lookupTomadorCep({ forceBanner: false }));
    document
      .querySelector("#form-tomador [name='cep']")
      ?.addEventListener("input", (ev) => {
        const d = digits(ev.target.value);
        if (d.length === 8) lookupTomadorCep({ forceBanner: false });
      });
    document
      .getElementById("tomador-document-type")
      ?.addEventListener("change", toggleTomadorCnpjFields);
  }

  global.HubCadastros = {
    bind,
    loadProviders,
    loadCustomers,
    applyWriterUi,
    canWrite,
  };
})(window);
