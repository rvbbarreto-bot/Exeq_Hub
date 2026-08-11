/** Preenche formulário de cadastro a partir da consulta CNPJ. */
(function () {
  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function setVal(name, value, locked) {
    const el = document.querySelector(`[name="${name}"]`);
    if (!el) return;
    el.value = value == null ? "" : String(value);
    const field = el.closest(".exeq-field");
    if (field && locked) {
      field.classList.add("is-locked");
      field.classList.remove("is-manual");
    }
  }

  function showBanner(kind, text) {
    const box = $("#lookup-banner");
    if (!box) return;
    box.hidden = false;
    box.className = "exeq-banner " + kind;
    box.textContent = text;
  }

  function digits(value) {
    return String(value || "").replace(/\D/g, "");
  }

  async function lookup(opts) {
    const documentInput = $('[name="document"]');
    const doc = digits(documentInput && documentInput.value);
    const bannerDefault =
      "Informe um CNPJ válido e consulte a Receita para pré-preencher.";

    if (opts.documentTypeSelect) {
      const dt = opts.documentTypeSelect.value;
      if (dt === "cpf") {
        showBanner(
          "info",
          "CPF: apenas validação de dígito. Nome e endereço são preenchimento manual (LGPD)."
        );
        return;
      }
    }

    if (doc.length !== 14) {
      showBanner("warn", "Informe um CNPJ com 14 dígitos para consultar.");
      return;
    }

    const btn = $("#btn-lookup");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Consultando…";
    }
    showBanner("info", "Consultando base cadastral…");

    const payload = {
      document: doc,
      force: !!opts.force,
      persist: !!opts.persist,
    };

    try {
      const headers = {
        "Content-Type": "application/json",
        Accept: "application/json",
      };
      if (opts.accessToken) {
        headers.Authorization = "Bearer " + opts.accessToken;
      }
      const csrf = document.querySelector("[name=csrfmiddlewaretoken]");
      if (csrf) headers["X-CSRFToken"] = csrf.value;

      const res = await fetch(opts.lookupUrl, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        credentials: "same-origin",
      });
      const data = await res.json().catch(function () {
        return {};
      });

      if (!res.ok) {
        showBanner(
          "warn",
          (data && data.detail) ||
            "Consulta indisponível. Continue com preenchimento manual."
        );
        return;
      }

      const nameField = opts.nameField || "legal_name";
      setVal(nameField, data.legal_name, true);
      if (opts.tradeNameField) {
        setVal(opts.tradeNameField, data.trade_name || "", true);
      }
      setVal("situacao_cadastral", data.situacao_cadastral || "", true);
      setVal("data_abertura", data.data_abertura || "", true);
      setVal("natureza_juridica", data.natureza_juridica || "", true);
      setVal("cnae_principal", data.cnae_principal || "", true);
      setVal("porte", data.porte || "", true);
      setVal("telefone_receita", data.telefone || "", true);
      setVal("email_receita", data.email || "", true);
      if (data.email && $('[name="email"]')) {
        setVal("email", data.email, false);
      }

      const addr = data.address || {};
      setVal("logradouro", addr.logradouro || "", true);
      setVal("numero", addr.numero || "", true);
      setVal("complemento", addr.complemento || "", true);
      setVal("bairro", addr.bairro || "", true);
      setVal("cep", addr.cep || "", true);
      setVal("municipio", addr.municipio || "", true);
      setVal("uf", addr.uf || "", true);
      setVal("codigo_municipio_ibge", addr.codigo_municipio_ibge || "", true);

      setVal("data_source", "receita_federal", false);
      setVal("receita_raw_payload", JSON.stringify(data.raw || {}), false);

      const extras = [];
      if (data.optante_simples === true) extras.push("indicador Simples Nacional");
      if (data.optante_mei === true) extras.push("indicador MEI");
      const suffix = extras.length ? " · " + extras.join(", ") : "";
      const cacheNote = data.cached ? " (cache local < 24h)" : "";
      showBanner(
        "ok",
        "Dado localizado e pronto para uso" + cacheNote + suffix + ". Revise e salve."
      );
    } catch (err) {
      showBanner(
        "warn",
        "Falha de rede na consulta. O formulário permanece editável manualmente."
      );
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = opts.buttonLabel || "Consultar Receita";
      }
    }
  }

  window.ExeqCadastroLookup = {
    bind: function (opts) {
      const btn = $("#btn-lookup");
      const refresh = $("#btn-refresh-lookup");
      if (btn) {
        btn.addEventListener("click", function (ev) {
          ev.preventDefault();
          lookup(Object.assign({}, opts, { force: false, persist: !!opts.objId }));
        });
      }
      if (refresh) {
        refresh.addEventListener("click", function (ev) {
          ev.preventDefault();
          lookup(
            Object.assign({}, opts, {
              force: true,
              persist: true,
              buttonLabel: "Atualizar dados da Receita",
            })
          );
        });
      }
      const dt = opts.documentTypeSelect;
      if (dt) {
        dt.addEventListener("change", function () {
          const cnpjOnly = document.querySelectorAll("[data-cnpj-only]");
          const isCpf = dt.value === "cpf";
          cnpjOnly.forEach(function (el) {
            el.hidden = isCpf;
          });
          if (isCpf) {
            showBanner(
              "info",
              "CPF: preenchimento 100% manual. Sem consulta cadastral (LGPD)."
            );
          } else {
            showBanner("info", bannerDefaultSafe());
          }
        });
        // Estado inicial (ex.: CPF na edição) sem depender de outro script.
        dt.dispatchEvent(new Event("change"));
      }
    },
  };

  function bannerDefaultSafe() {
    return "Informe um CNPJ válido e consulte a Receita para pré-preencher.";
  }
})();
