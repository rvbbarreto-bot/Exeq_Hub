(function () {
  "use strict";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }
  function csrfToken() {
    var el = qs("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }
  function parseJsonScript(id) {
    var el = document.getElementById(id);
    if (!el) return [];
    try {
      return JSON.parse(el.textContent || "[]");
    } catch (e) {
      return [];
    }
  }

  function formatNbsDisplay(code) {
    var d = String(code || "").replace(/\D/g, "").slice(0, 9);
    if (d.length !== 9) return String(code || "").trim();
    return d.charAt(0) + "." + d.slice(1, 5) + "." + d.slice(5, 7) + "." + d.slice(7, 9);
  }

  function initNbsPicker(root) {
    qsa("[data-nbs-picker]", root || document).forEach(function (wrap) {
      if (wrap.dataset.nbsInit === "1") return;
      wrap.dataset.nbsInit = "1";
      var codeInput = qs('input[name="codigo_nbs"]', wrap);
      var filterInput = qs("[data-nbs-picker-filter]", wrap);
      var selectEl = qs("[data-nbs-picker-select]", wrap);
      if (!codeInput || !selectEl) return;
      var searchUrl = wrap.getAttribute("data-nbs-search-url") || "/hub/nbs/search/";
      var timer = null;
      var pendingCode = codeInput.value || "";

      function optionLabel(row) {
        return (
          (row.display || formatNbsDisplay(row.codigo)) +
          " — " +
          (row.description || "")
        );
      }

      function ensureOption(code, description) {
        code = String(code || "").replace(/\D/g, "").slice(0, 9);
        if (code.length !== 9) return;
        for (var i = 0; i < selectEl.options.length; i++) {
          if (selectEl.options[i].value === code) {
            selectEl.value = code;
            codeInput.value = code;
            return;
          }
        }
        var opt = document.createElement("option");
        opt.value = code;
        opt.textContent =
          formatNbsDisplay(code) + (description ? " — " + description : "");
        selectEl.appendChild(opt);
        selectEl.value = code;
        codeInput.value = code;
      }

      function setCodeOnly(code, description) {
        code = String(code || "").replace(/\D/g, "").slice(0, 9);
        if (!code) {
          codeInput.value = "";
          selectEl.value = "";
          return;
        }
        pendingCode = code;
        ensureOption(code, description);
      }

      wrap.setNbsCode = setCodeOnly;

      function renderOptions(items) {
        var selected = codeInput.value || pendingCode || "";
        selectEl.innerHTML = "";
        var placeholder = document.createElement("option");
        placeholder.value = "";
        if (!items.length) {
          placeholder.textContent =
            "Nenhum código — importe o catálogo NBS (import_nbs_list)";
        } else {
          placeholder.textContent = "— Selecione um código NBS —";
        }
        selectEl.appendChild(placeholder);
        items.forEach(function (row) {
          var opt = document.createElement("option");
          opt.value = row.codigo || "";
          opt.textContent = optionLabel(row);
          selectEl.appendChild(opt);
        });
        if (selected) {
          ensureOption(selected, wrap.getAttribute("data-nbs-initial-desc") || "");
        }
      }

      function loadOptions(q) {
        fetch(searchUrl + "?q=" + encodeURIComponent(q || "") + "&limit=50", {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            if (data && (data.ok || data.results)) {
              renderOptions(data.results || []);
            }
          })
          .catch(function () {
            selectEl.innerHTML =
              '<option value="">Erro ao carregar lista NBS</option>';
          });
      }

      selectEl.addEventListener("change", function () {
        codeInput.value = selectEl.value || "";
        pendingCode = codeInput.value;
      });

      if (filterInput) {
        filterInput.addEventListener("input", function () {
          clearTimeout(timer);
          var q = (filterInput.value || "").trim();
          timer = setTimeout(function () {
            loadOptions(q);
          }, 280);
        });
      }

      loadOptions("");
      if (codeInput.value) {
        setCodeOnly(
          codeInput.value,
          wrap.getAttribute("data-nbs-initial-desc") || ""
        );
      }
    });
  }

  initNbsPicker(document);
  function showError(msg) {
    var box = qs("#wizard-step-error");
    if (!box) return;
    if (!msg) {
      box.hidden = true;
      box.textContent = "";
      return;
    }
    box.hidden = false;
    box.textContent = msg;
  }

  /* Drawer */
  var toggle = qs("[data-drawer-toggle]");
  var closeBtn = qs("[data-drawer-close]");
  var backdrop = qs("[data-drawer-backdrop]");
  function openDrawer() {
    document.body.classList.add("drawer-open");
  }
  function closeDrawer() {
    document.body.classList.remove("drawer-open");
  }
  if (toggle) toggle.addEventListener("click", openDrawer);
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (backdrop) backdrop.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      closeDrawer();
      var m = qs("#modal-confirm-emit");
      if (m) m.classList.remove("is-open");
    }
  });

  /* Wizard */
  var wiz = qs("[data-wizard]");
  if (wiz) {
    var panes = qsa("[data-wizard-pane]", wiz);
    var steps = qsa("[data-wizard-step]", wiz);
    var form = qs("#form-nfse-wizard", wiz);
    var current = 0;
    var lookupUrl = wiz.getAttribute("data-lookup-url") || "";
    var servicesIndex = {};
    parseJsonScript("hub-services-data").forEach(function (svc) {
      if (svc && svc.id) servicesIndex[String(svc.id)] = svc;
    });
    var profilesData = parseJsonScript("hub-profiles-data");
    var emitCoverage = new Set(parseJsonScript("hub-emit-coverage"));

    function serviceFromSelect(sel) {
      if (!sel || sel.selectedIndex < 0) return null;
      var opt = sel.options[sel.selectedIndex];
      if (!opt || !opt.value) return null;
      return servicesIndex[String(opt.value)] || null;
    }

    function selectedText(sel) {
      if (!sel || sel.selectedIndex < 0) return "—";
      return sel.options[sel.selectedIndex].text || "—";
    }

    function resolveProfileId() {
      var sel = qs("#id_fiscal_profile_id", form);
      if (sel && sel.value) return String(sel.value);
      if (profilesData.length && profilesData[0].id) {
        return String(profilesData[0].id);
      }
      return "";
    }

    function hasEmitRuleCoverage() {
      var svc = qs("#id_service_id", form);
      var ibge = qs("#id_ibge", form);
      var pid = resolveProfileId();
      var ibgeVal = ibge ? String(ibge.value || "").replace(/\D/g, "").slice(0, 7) : "";
      if (!svc || !svc.value || !pid || ibgeVal.length !== 7) return true;
      return emitCoverage.has(pid + "|" + ibgeVal + "|" + svc.value);
    }

    function fillCustomerFieldsFromSelect() {
      var sel = qs("#id_customer_id", form);
      if (!sel) return;
      var opt = sel.options[sel.selectedIndex];
      if (!opt || !opt.value) {
        qs("#id_customer_name").value = "";
        qs("#id_customer_email").value = "";
        qs("#id_customer_phone").value = "";
        return;
      }
      qs("#id_customer_name").value = opt.getAttribute("data-name") || "";
      qs("#id_customer_email").value = opt.getAttribute("data-email") || "";
      qs("#id_customer_phone").value = opt.getAttribute("data-phone") || "";
    }

    function fillServiceFields(fromChange) {
      var sel = qs("#id_service_id", form);
      if (!sel) return;
      var opt = sel.options[sel.selectedIndex];
      var descEl = form && form.elements.service_description;
      if (!opt || !opt.value) {
        qs("#id_lc116").value = "";
        if (descEl) descEl.value = "";
        var nbsWrap = qs("[data-nbs-picker]", form);
        if (nbsWrap && nbsWrap.setNbsCode) {
          nbsWrap.setNbsCode("", "");
        } else {
          var nbsEl = qs("#id_codigo_nbs", form);
          if (nbsEl) nbsEl.value = "";
        }
        return;
      }
      qs("#id_lc116").value =
        opt.getAttribute("data-lc116") || opt.getAttribute("data-code") || "";
      var svc = serviceFromSelect(sel);
      var svcNbs = (svc && svc.codigo_nbs) || opt.getAttribute("data-nbs") || "";
      var svcNbsDesc = (svc && svc.nbs_description) || "";
      var nbsWrap = qs("[data-nbs-picker]", form);
      if (nbsWrap && nbsWrap.setNbsCode) {
        if (fromChange || !String((qs('input[name="codigo_nbs"]', form) || {}).value || "").trim()) {
          nbsWrap.setNbsCode(svcNbs, svcNbsDesc);
        }
      } else {
        var nbsEl = qs("#id_codigo_nbs", form);
        if (nbsEl && (fromChange || !String(nbsEl.value || "").trim())) {
          nbsEl.value = svcNbs;
        }
      }
      if (descEl) {
        var catalogDesc =
          (svc && svc.description) || opt.getAttribute("data-description") || "";
        if (fromChange || !String(descEl.value || "").trim()) {
          descEl.value = catalogDesc;
        }
      }
    }

    function updateTaxPanels() {
      var profile = qs("#id_fiscal_profile_id", form);
      var opt = profile && profile.options[profile.selectedIndex];
      var isSimples = true;
      var retention = "";
      if (opt && opt.value) {
        isSimples = opt.getAttribute("data-is-simples") === "true";
        retention = opt.getAttribute("data-retention") || "";
      }
      var pS = qs("#tax-panel-simples");
      var pN = qs("#tax-panel-normal");
      var pR = qs("#tax-panel-retencao");
      if (pS) {
        pS.hidden = !isSimples;
        pS.classList.toggle("is-visible", isSimples);
      }
      if (pN) {
        pN.hidden = isSimples;
        pN.classList.toggle("is-visible", !isSimples);
      }
      var showRet = retention && retention !== "by_rule" && retention !== "";
      if (pR) {
        pR.hidden = !showRet;
        var hint = qs("#id_iss_retido_hint");
        if (hint) hint.value = retention || "";
      }
    }

    function formField(name) {
      if (!form || !form.elements) return "";
      var el = form.elements[name];
      if (!el || el.disabled) return "";
      return String(el.value || "").trim();
    }

    function selectedServiceDescription() {
      var sel = qs("#id_service_id", form);
      var svc = serviceFromSelect(sel);
      if (svc && svc.description) return String(svc.description).trim();
      if (!sel || sel.selectedIndex < 0) return "";
      var opt = sel.options[sel.selectedIndex];
      if (!opt || !opt.value) return "";
      return (opt.getAttribute("data-description") || "").trim();
    }

    function setReviewText(key, text, emptyLabel) {
      var el =
        qs('[data-review="' + key + '"]', form) ||
        qs('[data-review="' + key + '"]');
      if (!el) return;
      var hasText = Boolean(text);
      el.textContent = hasText ? text : emptyLabel || "—";
      el.classList.toggle("review-text--empty", !hasText);
    }

    function truncateText(text, max) {
      if (!text) return "—";
      if (text.length <= max) return text;
      return text.slice(0, max - 1) + "…";
    }

    function updateReview() {
      fillServiceFields(false);
      var tomador = selectedText(qs("#id_customer_id", form));
      var servico = selectedText(qs("#id_service_id", form));
      var perfil = selectedText(qs("#id_fiscal_profile_id", form));
      var amount = formField("amount") || "—";
      var compDate = formField("competence_date") || "—";
      var descricao =
        formField("service_description") || selectedServiceDescription();
      var infoCompl = formField("informacoes_complementares");
      var map = {
        tomador: tomador,
        servico: servico,
        tributacao: perfil,
        valor: amount ? "R$ " + amount : "—",
        competencia: compDate,
      };
      Object.keys(map).forEach(function (k) {
        var el =
          qs('[data-review="' + k + '"]', form) ||
          qs('[data-review="' + k + '"]');
        if (el) el.textContent = map[k];
      });
      setReviewText("descricao", descricao, "—");
      setReviewText("info_compl", infoCompl, "(não informado)");
    }

    function validateStep(n) {
      showError("");
      if (n === 0) {
        var c = qs("#id_customer_id", form);
        if (!c || !c.value) {
          showError("Selecione um tomador cadastrado para continuar.");
          return false;
        }
      }
      if (n === 1) {
        var s = qs("#id_service_id", form);
        var a = qs("#id_amount", form);
        var d = qs("#id_competence_date", form);
        if (!s || !s.value) {
          showError("Selecione o serviço.");
          return false;
        }
        if (!d || !d.value) {
          showError("Informe a competência.");
          return false;
        }
        if (!a || !String(a.value).trim()) {
          showError("Informe o valor da nota.");
          return false;
        }
        var desc = form.elements.service_description;
        if (!desc || !String(desc.value || "").trim()) {
          showError("Informe a descrição do serviço na nota.");
          return false;
        }
      }
      if (n === 2) {
        var p = qs("#id_provider_id", form);
        if (!p || !p.value) {
          showError("Selecione o prestador.");
          return false;
        }
        var ibge = qs("#id_ibge", form);
        var ibgeVal = ibge ? String(ibge.value || "").replace(/\D/g, "") : "";
        if (!ibgeVal || ibgeVal.length !== 7) {
          showError("Informe o IBGE do município da prestação (7 dígitos).");
          return false;
        }
        if (!hasEmitRuleCoverage()) {
          var svcOpt =
            qs("#id_service_id", form) &&
            qs("#id_service_id", form).options[
              qs("#id_service_id", form).selectedIndex
            ];
          var svcCode =
            (svcOpt && (svcOpt.getAttribute("data-code") || svcOpt.text)) || "serviço";
          showError(
            "Sem regra ISS publicada para " +
              svcCode +
              " no IBGE " +
              ibgeVal +
              ". Complete a matriz em Fiscal → Pronto p/ emitir ou Regras ISS."
          );
          return false;
        }
      }
      return true;
    }

    function validateThrough(targetIndex) {
      for (var i = 0; i < targetIndex; i++) {
        if (!validateStep(i)) {
          showStep(i);
          return false;
        }
      }
      return true;
    }

    function showStep(n) {
      current = n;
      panes.forEach(function (p, i) {
        p.classList.toggle("is-active", i === n);
      });
      steps.forEach(function (s, i) {
        s.classList.toggle("is-active", i === n);
        s.classList.toggle("is-done", i < n);
        if (i === n) s.setAttribute("aria-current", "step");
        else s.removeAttribute("aria-current");
      });
      if (n === 3) updateReview();
      showError("");
    }

    function go(n) {
      if (n < 0 || n >= panes.length) return;
      if (n > current) {
        for (var i = 0; i < n; i++) {
          if (!validateStep(i)) {
            showStep(i);
            return;
          }
        }
      }
      showStep(n);
    }

    qsa("[data-wizard-next]", wiz).forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!validateStep(current)) return;
        go(current + 1);
      });
    });
    qsa("[data-wizard-prev]", wiz).forEach(function (btn) {
      btn.addEventListener("click", function () {
        go(current - 1);
      });
    });
    steps.forEach(function (s, i) {
      s.addEventListener("click", function () {
        if (i === current) return;
        go(i);
      });
    });

    ["service_description", "informacoes_complementares"].forEach(function (name) {
      var el = form && form.elements[name];
      if (!el) return;
      el.addEventListener("input", function () {
        if (current === 3) updateReview();
      });
    });

    var custSel = qs("#id_customer_id", form);
    if (custSel) custSel.addEventListener("change", fillCustomerFieldsFromSelect);
    var svcSel = qs("#id_service_id", form);
    if (svcSel) svcSel.addEventListener("change", function () { fillServiceFields(true); });
    var profileSel = qs("#id_fiscal_profile_id", form);
    if (profileSel) profileSel.addEventListener("change", updateTaxPanels);
    var provSel = qs("#id_provider_id", form);
    var ibgeInput = qs("#id_ibge", form);
    if (provSel && ibgeInput) {
      provSel.addEventListener("change", function () {
        var opt = provSel.options[provSel.selectedIndex];
        var defIbge = opt && opt.getAttribute("data-ibge");
        if (defIbge && (!ibgeInput.value || ibgeInput.dataset.autoFilled === "1")) {
          ibgeInput.value = String(defIbge).replace(/\D/g, "").slice(0, 7);
          ibgeInput.dataset.autoFilled = "1";
        }
      });
      ibgeInput.addEventListener("input", function () {
        ibgeInput.dataset.autoFilled = "0";
      });
    }

    /* Lookup AJAX */
    var btnLookup = qs("#btn-lookup-doc");
    var lookupInput = qs("#lookup_doc");
    var fbOk = qs("#lookup-feedback");
    var fbErr = qs("#lookup-error");
    if (btnLookup && lookupInput) {
      btnLookup.addEventListener("click", function () {
        var doc = String(lookupInput.value || "").replace(/\D/g, "");
        if (fbOk) fbOk.hidden = true;
        if (fbErr) {
          fbErr.hidden = true;
          fbErr.textContent = "";
        }
        if (doc.length < 11) {
          if (fbErr) {
            fbErr.hidden = false;
            fbErr.textContent = "Informe CPF (11) ou CNPJ (14) com dígitos válidos.";
          }
          return;
        }
        btnLookup.disabled = true;
        btnLookup.textContent = "Buscando…";
        var url = lookupUrl + (lookupUrl.indexOf("?") >= 0 ? "&" : "?") + "document=" + encodeURIComponent(doc);
        fetch(url, {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
        })
          .then(function (r) {
            return r.json().then(function (body) {
              return { ok: r.ok, body: body };
            });
          })
          .then(function (res) {
            if (!res.ok || !res.body.ok) {
              if (fbErr) {
                fbErr.hidden = false;
                fbErr.textContent =
                  (res.body && res.body.error) || "Consulta indisponível.";
              }
              return;
            }
            var data = res.body.data || {};
            if (fbOk) {
              fbOk.hidden = false;
              fbOk.textContent = data.message || "✓ Tomador encontrado";
            }
            if (data.customer_id && custSel) {
              custSel.value = data.customer_id;
              fillCustomerFieldsFromSelect();
            } else {
              qs("#id_customer_name").value = data.name || "";
              qs("#id_customer_email").value = data.email || "";
              qs("#id_customer_phone").value = data.phone || "";
            }
          })
          .catch(function () {
            if (fbErr) {
              fbErr.hidden = false;
              fbErr.textContent = "Falha de rede na consulta.";
            }
          })
          .finally(function () {
            btnLookup.disabled = false;
            btnLookup.textContent = "Buscar";
          });
      });
    }

    /* Confirm modal + draft save */
    var modal = qs("#modal-confirm-emit");
    var draftBtn = qs("[data-save-draft]", wiz);
    if (draftBtn && form) {
      draftBtn.addEventListener("click", function () {
        if (!validateThrough(3)) {
          return;
        }
        var actionEl = form.querySelector('[name="wizard_action"]');
        var confirmEl = form.querySelector('[name="confirm_emit"]');
        if (actionEl) actionEl.value = "save_draft";
        if (confirmEl) confirmEl.value = "0";
        form.submit();
      });
    }
    if (form && modal) {
      form.addEventListener("submit", function (e) {
        var actionEl = form.querySelector('[name="wizard_action"]');
        var isDraft =
          actionEl && actionEl.value === "save_draft";
        if (isDraft) {
          return;
        }
        if (form.querySelector('[name="confirm_emit"]').value !== "1") {
          e.preventDefault();
          if (!validateThrough(3)) {
            return;
          }
          updateReview();
          qs("[data-sum-tomador]").textContent = selectedText(
            qs("#id_customer_id", form)
          );
          qs("[data-sum-amount]").textContent =
            "R$ " + ((qs("#id_amount", form) || {}).value || "—");
          qs("[data-sum-comp]").textContent =
            (qs("#id_competence_date", form) || {}).value || "—";
          var sumS = qs("[data-sum-servico]");
          if (sumS)
            sumS.textContent = selectedText(qs("#id_service_id", form));
          var sumDesc = qs("[data-sum-descricao]");
          if (sumDesc) {
            var descText =
              formField("service_description") || selectedServiceDescription();
            sumDesc.textContent = truncateText(descText, 160);
          }
          var infoCompl = formField("informacoes_complementares");
          var sumInfo = qs("[data-sum-info-compl]");
          var infoLine = qs("#modal-info-compl-line", modal);
          if (sumInfo) sumInfo.textContent = truncateText(infoCompl, 120);
          if (infoLine) infoLine.hidden = !infoCompl;
          modal.classList.add("is-open");
          var focusBtn = qs("[data-modal-confirm]", modal);
          if (focusBtn) focusBtn.focus();
        }
      });
      var cancel = qs("[data-modal-cancel]", modal);
      var ok = qs("[data-modal-confirm]", modal);
      if (cancel)
        cancel.addEventListener("click", function () {
          modal.classList.remove("is-open");
        });
      if (ok)
        ok.addEventListener("click", function () {
          var actionEl = form.querySelector('[name="wizard_action"]');
          if (actionEl) actionEl.value = "emit";
          form.querySelector('[name="confirm_emit"]').value = "1";
          modal.classList.remove("is-open");
          form.submit();
        });
    }

    fillCustomerFieldsFromSelect();
    fillServiceFields(false);
    updateTaxPanels();
    var initialStep = parseInt(wiz.getAttribute("data-initial-step") || "0", 10);
    if (isNaN(initialStep) || initialStep < 0 || initialStep >= panes.length) {
      initialStep = 0;
    }
    showStep(initialStep);
  }

  /* Doc tabs */
  qsa("[data-tab-group]").forEach(function (group) {
    var buttons = qsa("[data-tab]", group);
    var panels = qsa("[data-tab-panel]", group);
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-tab");
        buttons.forEach(function (b) {
          b.classList.toggle("is-active", b === btn);
          b.setAttribute("aria-selected", b === btn ? "true" : "false");
        });
        panels.forEach(function (p) {
          p.hidden = p.getAttribute("data-tab-panel") !== id;
        });
      });
    });
  });

  /* Copy JSON */
  qsa("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var sel = btn.getAttribute("data-copy");
      var el = qs(sel);
      if (!el) return;
      var text = el.textContent || "";
      var label = btn.textContent;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          btn.textContent = "Copiado";
          setTimeout(function () {
            btn.textContent = label || "Copiar JSON";
          }, 1500);
        });
      }
    });
  });

  /* Mobile filter toggle */
  var filterToggle = qs("[data-filter-toggle]");
  var filterBar = qs("[data-filter-bar]");
  if (filterToggle && filterBar) {
    filterToggle.addEventListener("click", function () {
      filterBar.classList.toggle("mobile-collapsed");
    });
  }

  /* Provider form: CNPJ mask + Receita lookup (sessão Hub) */
  (function initProviderForm() {
    var root = qs("[data-provider-form]");
    if (!root) return;
    var lookupUrl = root.getAttribute("data-lookup-url") || "";
    var docEl = qs("#id_document", root);
    var banner = qs("#lookup-banner", root);
    var btn = qs("#btn-lookup", root);
    var rawEl = qs("#id_receita_raw_payload", root);
    var sourceEl = qs('[name="data_source"]', root);

    function onlyDigits(v) {
      return String(v || "").replace(/\D/g, "");
    }
    function formatCnpj(d) {
      d = onlyDigits(d).slice(0, 14);
      if (d.length <= 2) return d;
      if (d.length <= 5) return d.slice(0, 2) + "." + d.slice(2);
      if (d.length <= 8) return d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5);
      if (d.length <= 12) {
        return d.slice(0, 2) + "." + d.slice(2, 5) + "." + d.slice(5, 8) + "/" + d.slice(8);
      }
      return (
        d.slice(0, 2) +
        "." +
        d.slice(2, 5) +
        "." +
        d.slice(5, 8) +
        "/" +
        d.slice(8, 12) +
        "-" +
        d.slice(12)
      );
    }
    function applyMask() {
      if (!docEl) return;
      docEl.value = formatCnpj(docEl.value);
      docEl.maxLength = 18;
    }
    function setBanner(kind, text) {
      if (!banner) return;
      banner.hidden = false;
      banner.className = "lookup-banner " + kind;
      banner.textContent = text;
    }
    function setVal(name, value) {
      var el = qs('[name="' + name + '"]', root);
      if (el && value != null) el.value = String(value);
    }
    if (docEl) {
      docEl.addEventListener("input", applyMask);
      docEl.addEventListener("blur", applyMask);
      applyMask();
    }
    var seed = document.getElementById("receita-raw-seed");
    if (seed && rawEl) {
      rawEl.value = seed.textContent || "";
    }
    if (btn && lookupUrl) {
      btn.addEventListener("click", function () {
        var doc = onlyDigits(docEl && docEl.value);
        if (doc.length !== 14) {
          setBanner("warn", "Informe um CNPJ com 14 dígitos para consultar.");
          return;
        }
        btn.disabled = true;
        btn.textContent = "Consultando…";
        setBanner("info", "Consultando base cadastral…");
        fetch(lookupUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-CSRFToken": csrfToken()
          },
          credentials: "same-origin",
          body: JSON.stringify({ document: doc, force: false })
        })
          .then(function (res) {
            return res.json().then(function (data) {
              return { ok: res.ok, data: data };
            });
          })
          .then(function (result) {
            if (!result.ok || !result.data || result.data.ok === false) {
              setBanner("err", (result.data && result.data.error) || "Consulta indisponível.");
              return;
            }
            var d = result.data;
            setVal("legal_name", d.legal_name);
            setVal("trade_name", d.trade_name);
            setVal("situacao_cadastral", d.situacao_cadastral);
            if (d.data_abertura) {
              setVal("data_abertura", String(d.data_abertura).slice(0, 10));
            }
            setVal("natureza_juridica", d.natureza_juridica);
            setVal("cnae_principal", d.cnae_principal);
            setVal("porte", d.porte);
            setVal("telefone_receita", d.telefone);
            setVal("email_receita", d.email);
            var addr = d.address || {};
            setVal("logradouro", addr.logradouro);
            setVal("numero", addr.numero);
            setVal("complemento", addr.complemento);
            setVal("bairro", addr.bairro);
            setVal("cep", addr.cep);
            setVal("municipio", addr.municipio);
            setVal("uf", addr.uf);
            setVal("codigo_municipio_ibge", addr.codigo_municipio_ibge || addr.codigo_ibge);
            if (sourceEl) sourceEl.value = "receita";
            if (rawEl) rawEl.value = JSON.stringify(d.raw || {});
            setBanner("ok", d.cached ? "Dados do cache cadastral." : "Dados da Receita aplicados.");
          })
          .catch(function () {
            setBanner("err", "Falha de rede na consulta.");
          })
          .finally(function () {
            btn.disabled = false;
            btn.textContent = "Consultar Receita";
          });
      });
    }
  })();
})();
