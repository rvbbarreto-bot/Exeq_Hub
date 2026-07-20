from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.issuance.focus_webhook import (
    FocusNfseWebhookNotFoundError,
    InvalidFocusWebhookAuthError,
    ingest_focus_nfse_webhook,
)
from apps.issuance.exceptions import InvalidTransitionError


class FocusNfseWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        auth = request.headers.get(
            "X-Focus-Authorization",
            request.headers.get("Authorization", ""),
        )
        try:
            inbox = ingest_focus_nfse_webhook(
                raw_authorization=auth,
                payload=payload,
            )
        except InvalidFocusWebhookAuthError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=401)
        except FocusNfseWebhookNotFoundError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=404)
        except InvalidTransitionError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(
            {
                "id": str(inbox.id),
                "status": inbox.status,
                "provider": inbox.provider,
            },
            status=200,
        )
