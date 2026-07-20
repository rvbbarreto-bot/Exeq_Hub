from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.auth_services import authenticate_for_tenant, issue_tokens
from apps.accounts.serializers import LoginSerializer
from shared.exceptions import AuthenticationError


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user, membership = authenticate_for_tenant(**serializer.validated_data)
        except AuthenticationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(issue_tokens(user, membership), status=status.HTTP_200_OK)


class RefreshView(TokenRefreshView):
    authentication_classes = []
    permission_classes = [AllowAny]
