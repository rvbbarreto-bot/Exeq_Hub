from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsTenantWriter
from apps.issuance.exceptions import (
    CancelJustificationError,
    FocusCancelFailedError,
    InvalidTransitionError,
)
from apps.issuance.models import NfIssue
from apps.issuance.serializers import (
    NfIssueCancelSerializer,
    NfIssueCreateSerializer,
    NfIssueSerializer,
)
from apps.issuance.services import cancel_nf_issue, reprocess_nf_issue


class NfIssueViewSet(viewsets.ModelViewSet):
    permission_classes = [IsTenantWriter]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return NfIssue.objects.filter(tenant=self.request.tenant).order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return NfIssueCreateSerializer
        return NfIssueSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issue = serializer.save()
        return Response(NfIssueSerializer(issue).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        issue = self.get_object()
        serializer = NfIssueCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cancel_nf_issue(
                issue,
                justificativa=serializer.validated_data["justificativa"],
                codigo_cancelamento=serializer.validated_data.get("codigo_cancelamento"),
            )
        except (InvalidTransitionError, CancelJustificationError, FocusCancelFailedError) as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)
        issue.refresh_from_db()
        return Response(NfIssueSerializer(issue).data)

    @action(detail=True, methods=["post"], url_path="reprocess")
    def reprocess(self, request, pk=None):
        issue = self.get_object()
        try:
            reprocess_nf_issue(issue)
        except InvalidTransitionError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)
        issue.refresh_from_db()
        return Response(NfIssueSerializer(issue).data)
