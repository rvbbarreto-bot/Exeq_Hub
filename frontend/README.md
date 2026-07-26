# Frontend HTML/JS do EXEQ Hub (layout v2 + API no mesmo BD do Admin).

Servir com o Django:

- App: http://127.0.0.1:8000/app/
- JS: http://127.0.0.1:8000/app/js/hub-api.js (etc.)

Telas ligadas à API (PostgreSQL / ORM Django — mesmos dados do `/admin/`):

- **Painel** — KPIs + status + últimas cobranças + certificados (`hub-dashboard.js`)
- **Emissão NFS-e**, **Cobranças**, **Provedor de cobrança**, **Certificados A1**, **Guias DAS**

Séries mensais de protótipo foram removidas; gráficos doughnut usam `/charges/summary/` e `/nf-issue/summary/`.
