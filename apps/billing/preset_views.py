"""API — predefinições de cobrança do tenant."""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantMember, IsTenantWriter
from apps.billing.exceptions import InvalidBillingPresetError
from apps.billing.presets import get_billing_preset, set_billing_preset


class BillingPresetView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsTenantMember()]
        return [IsTenantWriter()]

    def get(self, request):
        return Response(get_billing_preset(tenant=request.tenant))

    def put(self, request):
        try:
            data = set_billing_preset(tenant=request.tenant, preset=request.data)
        except InvalidBillingPresetError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)
        return Response(data, status=200)
