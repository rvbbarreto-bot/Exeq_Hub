"""Escopo piloto Food — autorizado pelo PO (2026-08-21).

Telas fora deste conjunto não aparecem na navegação Hub/Admin.
URLs legadas respondem 404 com página explicativa (sem redirect).
"""

from __future__ import annotations

PILOT_HUB_SECTIONS: frozenset[str] = frozenset(
    {"orders", "products", "customers", "production"}
)

PILOT_ADMIN_MODELS: frozenset[str] = frozenset(
    {
        "FoodCustomer",
        "FoodProduct",
        "FoodOrder",
        "FoodBom",
        "FoodProductionOrder",
        "FoodPayment",
        "FoodPaymentEvent",
    }
)

HUB_SECTION_LABELS: dict[str, str] = {
    "orders": "Pedidos",
    "products": "Produtos",
    "customers": "Clientes",
    "purchases": "Compras",
    "production": "Produção",
    "retention": "Régua",
    "marketplace": "Marketplace",
    "intelligence": "Inteligência",
}

HUB_SECTION_URL_NAMES: dict[str, str] = {
    "orders": "hub-v4-food-orders",
    "products": "hub-v4-food-products",
    "customers": "hub-v4-food-customers",
    "purchases": "hub-v4-food-purchases",
    "production": "hub-v4-food-production",
    "retention": "hub-v4-food-retention",
    "marketplace": "hub-v4-food-marketplace",
    "intelligence": "hub-v4-food-intelligence",
}

HUB_SECTION_NAV_KEYS: dict[str, str] = {
    "orders": "food",
    "products": "food_products",
    "customers": "food_customers",
    "purchases": "food_purchases",
    "production": "food_production",
    "retention": "food_retention",
    "marketplace": "food_marketplace",
    "intelligence": "food_intelligence",
}

HUB_SECTION_ORDER: tuple[str, ...] = (
    "orders",
    "products",
    "customers",
    "production",
    "purchases",
    "retention",
    "marketplace",
    "intelligence",
)


def hub_section_in_pilot(section: str) -> bool:
    return section in PILOT_HUB_SECTIONS


def admin_model_in_pilot(object_name: str) -> bool:
    return object_name in PILOT_ADMIN_MODELS
