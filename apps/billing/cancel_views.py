"""Motivos de cancelamento expostos à API/Hub (espelho Inter)."""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantMember
from integrations.payments.inter_cancel import (
    DEFAULT_INTER_CANCEL_MOTIVO,
    INTER_CANCEL_MOTIVOS,
)

# Rótulos PT-BR para UI (valores = enum Inter).
MOTIVO_LABELS = {
    "ACERTOS": "Acertos",
    "APEDIDODOCLIENTE": "A pedido do cliente",
    "CLIENTE_DESISTIU": "Cliente desistiu",
    "PAGODIRETOAOCLIENTE": "Pago direto ao cliente",
    "SUBSTITUICAO": "Substituição",
}


class CancelMotivosView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        motivos = [
            {"value": m, "label": MOTIVO_LABELS.get(m, m)}
            for m in sorted(INTER_CANCEL_MOTIVOS)
        ]
        return Response(
            {
                "default": DEFAULT_INTER_CANCEL_MOTIVO,
                "motivos": motivos,
            }
        )
