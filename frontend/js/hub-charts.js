/** EXEQ Hub — Chart.js helpers (dados reais; render só em tela visível). */
(function (global) {
  "use strict";

  /** @type {Record<string, { destroy: Function, resize: Function }>} */
  const instances = {};

  function chartCtor() {
    const C = global.Chart;
    if (typeof C === "function") return C;
    if (C && typeof C.Chart === "function") return C.Chart;
    return null;
  }

  function themeVar(name, fallback) {
    const v = getComputedStyle(document.body).getPropertyValue(name).trim();
    return v || fallback;
  }

  function palette() {
    return {
      text: themeVar("--text-muted", "#726F66"),
      grid: themeVar("--border", "#E4E2D9"),
      accent: themeVar("--accent", "#FFDD1A"),
      success: themeVar("--success", "#0F8A4B"),
      danger: themeVar("--danger", "#C22626"),
      warning: themeVar("--warning", "#B5790A"),
      info: themeVar("--info", "#1D4ED8"),
      neutral: themeVar("--text-muted", "#726F66"),
    };
  }

  function destroy(id) {
    if (instances[id]) {
      try {
        instances[id].destroy();
      } catch {
        /* ignore */
      }
      delete instances[id];
    }
  }

  function isCanvasVisible(canvas) {
    if (!canvas || !canvas.isConnected) return false;
    const screen = canvas.closest(".screen");
    if (screen && !screen.classList.contains("active")) return false;
    const box = canvas.parentElement;
    if (!box) return false;
    return box.clientWidth > 0 && box.clientHeight > 0;
  }

  function showPlaceholder(canvas, message) {
    const box = canvas.parentElement;
    if (!box) return;
    let tip = box.querySelector(".chart-empty");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "chart-empty";
      box.appendChild(tip);
    }
    tip.hidden = false;
    tip.textContent = message;
    canvas.style.visibility = "hidden";
  }

  function hidePlaceholder(canvas) {
    const box = canvas.parentElement;
    if (!box) return;
    const tip = box.querySelector(".chart-empty");
    if (tip) tip.hidden = true;
    canvas.style.visibility = "visible";
  }

  /**
   * Barras horizontais — padrão usuais em dashboards financeiros/contábeis
   * para comparar categorias/status (melhor leitura que pizza/rosca).
   * @param {string} canvasId
   * @param {{ labels: string[], values: number[], colors?: string[] }} opts
   */
  function renderStatusBars(canvasId, opts) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const Ctor = chartCtor();
    if (!Ctor) {
      showPlaceholder(canvas, "Chart.js indisponível");
      return;
    }

    if (!isCanvasVisible(canvas)) {
      requestAnimationFrame(() => {
        if (isCanvasVisible(canvas)) renderStatusBars(canvasId, opts);
      });
      return;
    }

    destroy(canvasId);
    hidePlaceholder(canvas);

    const col = palette();
    const labels = opts.labels || [];
    const values = (opts.values || []).map((n) => Number(n) || 0);
    const total = values.reduce((a, b) => a + b, 0);
    if (!total) {
      showPlaceholder(canvas, "Sem dados no tenant");
      return;
    }

    const colors =
      opts.colors ||
      [col.success, col.info, col.warning, col.danger, col.neutral, col.accent];

    const box = canvas.parentElement;
    if (box) {
      const h = Math.max(200, labels.length * 42 + 48);
      box.style.height = `${h}px`;
    }

    if (Ctor.defaults) {
      Ctor.defaults.font.family = "'Inter', sans-serif";
      Ctor.defaults.font.size = 11;
      Ctor.defaults.color = col.text;
    }

    const chart = new Ctor(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: colors.slice(0, labels.length),
            borderWidth: 0,
            borderRadius: 6,
            maxBarThickness: 28,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(ctx) {
                const n = Number(ctx.raw) || 0;
                return ` ${n}`;
              },
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { precision: 0, color: col.text },
            grid: { color: col.grid },
            border: { display: false },
          },
          y: {
            ticks: { color: col.text },
            grid: { display: false },
            border: { display: false },
          },
        },
      },
    });
    instances[canvasId] = chart;
    requestAnimationFrame(() => {
      try {
        chart.resize();
      } catch {
        /* ignore */
      }
    });
  }

  /** @deprecated Prefer renderStatusBars — mantido como alias. */
  function renderDoughnut(canvasId, opts) {
    return renderStatusBars(canvasId, opts);
  }

  function rebuildVisible() {
    const active = document.querySelector(".screen.active");
    if (!active) return;
    if (active.id === "screen-dashboard" && global.HubDashboard?.renderCharts) {
      HubDashboard.renderCharts();
    }
    if (active.id === "screen-cobrancas" && global.HubCharges?.renderCharts) {
      HubCharges.renderCharts();
    }
    if (active.id === "screen-nfse" && global.HubNfse?.renderCharts) {
      HubNfse.renderCharts();
    }
  }

  global.HubCharts = {
    destroy,
    renderStatusBars,
    renderDoughnut,
    palette,
    rebuildVisible,
    chartCtor,
  };
})(window);
