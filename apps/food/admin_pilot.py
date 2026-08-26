"""Admin Food — bloqueio de CRUD fora do escopo piloto (índice continua visível)."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.food.pilot_scope import admin_model_in_pilot


class FoodPilotAdminMixin:
    def _pilot_enabled(self) -> bool:
        return admin_model_in_pilot(self.model._meta.object_name)

    def _pilot_block_response(self, request):
        messages.info(
            request,
            "Este cadastro está fora do escopo piloto Food e será habilitado em breve.",
        )
        return HttpResponseRedirect(reverse("admin:app_list", args=["food"]))

    def changelist_view(self, request, extra_context=None):
        if not self._pilot_enabled():
            return self._pilot_block_response(request)
        return super().changelist_view(request, extra_context=extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        if not self._pilot_enabled():
            return self._pilot_block_response(request)
        return super().add_view(request, form_url=form_url, extra_context=extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self._pilot_enabled():
            return self._pilot_block_response(request)
        return super().change_view(
            request, object_id, form_url=form_url, extra_context=extra_context
        )

    def delete_view(self, request, object_id, extra_context=None):
        if not self._pilot_enabled():
            return self._pilot_block_response(request)
        return super().delete_view(request, object_id, extra_context=extra_context)
