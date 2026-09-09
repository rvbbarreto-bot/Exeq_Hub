"""
Hub V4 — navegação lateral (espelho da spec PO / UNFOLD SIDEBAR).

URLs resolvidas via url_name em runtime (apps/hub_v4/sidebar.py).
Itens com ``flag`` só aparecem quando a flag do context processor está True.
"""

HUB_V4_SIDEBAR = {
    "show_search": False,
    "show_all_applications": False,
    "navigation": [
        {
            "title": "Dashboard",
            "separator": False,
            "collapsible": False,
            "items": [
                {
                    "title": "Painel Geral",
                    "icon": "dashboard",
                    "url_name": "hub-v4-dashboard",
                    "nav": "dashboard",
                },
            ],
        },
        {
            "title": "Exeq Fiscal",
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": "Emissão NF-e",
                    "icon": "receipt_long",
                    "url_name": "hub-v4-nfe-list",
                    "nav": "nfe",
                    "flag": "nfe_enabled_nav",
                },
                {
                    "title": "NF-e de Entrada",
                    "icon": "move_to_inbox",
                    "url_name": "hub-v4-nfe-entrada-list",
                    "nav": "nfe_entrada",
                    "flag": "nfe_entrada_enabled_nav",
                },
                {
                    "title": "Emissão NFC-e avulsa",
                    "icon": "point_of_sale",
                    "url_name": "hub-v4-nfce-list",
                    "nav": "nfce",
                    "flag": "nfce_enabled_nav",
                },
                {
                    "title": "Emissão NFS-e",
                    "icon": "description",
                    "url_name": "hub-v4-nfse-list",
                    "nav": "nfse",
                    "flag": "nfse_enabled_nav",
                },
                {
                    "title": "Apuração Guia DAS",
                    "icon": "request_quote",
                    "url_name": "hub-v4-das",
                    "nav": "das",
                },
                {
                    "title": "Perfis fiscais",
                    "icon": "account_balance",
                    "url_name": "hub-v4-fiscal",
                    "nav": "fiscal",
                    "flag": "nfse_enabled_nav",
                },
                {
                    "title": "Regras ISS",
                    "icon": "rule",
                    "url_name": "hub-v4-tax-rules",
                    "nav": "fiscal_rules",
                    "flag": "nfse_enabled_nav",
                },
                {
                    "title": "Pronto p/ emitir",
                    "icon": "task_alt",
                    "url_name": "hub-v4-fiscal-readiness",
                    "nav": "fiscal_readiness",
                    "flag": "nfse_enabled_nav",
                },
                {
                    "title": "Serviços",
                    "icon": "design_services",
                    "url_name": "hub-v4-services",
                    "nav": "services",
                    "flag": "nfse_enabled_nav",
                },
                {
                    "title": "Food",
                    "icon": "restaurant",
                    "url_name": "hub-v4-food-orders",
                    "nav": "food",
                },
            ],
        },
        {
            "title": "Cadastro Empresa",
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": "Empresas",
                    "icon": "domain",
                    "url_name": "hub-v4-providers",
                    "nav": "providers",
                },
                {
                    "title": "Produtos NF-e",
                    "icon": "inventory_2",
                    "url_name": "hub-v4-nfe-products",
                    "nav": "nfe_products",
                    "flag": "nfe_enabled_nav",
                },
                {
                    "title": "Clientes",
                    "icon": "group",
                    "url_name": "hub-v4-customers",
                    "nav": "customers",
                },
                {
                    "title": "Usuários",
                    "icon": "manage_accounts",
                    "url_name": "hub-v4-users",
                    "nav": "users",
                },
                {
                    "title": "Certificados",
                    "icon": "verified_user",
                    "url_name": "hub-v4-certificates",
                    "nav": "certificates",
                },
                {
                    "title": "Integrações",
                    "icon": "hub",
                    "url_name": "hub-v4-integrations",
                    "nav": "integrations",
                },
                {
                    "title": "Preferências",
                    "icon": "settings",
                    "url_name": "hub-v4-preferences",
                    "nav": "preferences",
                },
            ],
        },
        {
            "title": "Financeiro",
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": "Cobrança",
                    "icon": "payments",
                    "url_name": "hub-v4-charges",
                    "nav": "charges",
                },
            ],
        },
    ],
}
