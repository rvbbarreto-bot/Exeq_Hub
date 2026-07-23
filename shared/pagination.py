"""Paginação padrão do Hub (opt-in por ViewSet — não global)."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class HubPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"
