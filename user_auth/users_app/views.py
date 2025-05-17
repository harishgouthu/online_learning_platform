
from rest_framework import status, viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

from dj_rest_auth.registration.views import RegisterView, SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter

from .models import Profile
from .serializers import (
    CustomRegisterSerializer,
    CustomTokenObtainPairSerializer,
    ProfileSerializer,
)

import logging
import requests

logger = logging.getLogger(__name__)


class CustomRegisterView(RegisterView):
    serializer_class = CustomRegisterSerializer

    def get_response_data(self, user):
        return {"message": "Registered successfully"}


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter

    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            response.data['message'] = "Google login successful"
            return response
        except Exception as e:
            return Response({
                "error": "Google login failed",
                "details": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    def post(self, request):
        try:
            refresh_token = request.COOKIES.get("refresh_token")
            access_token = request.COOKIES.get("access_token")

            if refresh_token:
                RefreshToken(refresh_token).blacklist()
                logger.info("Refresh token blacklisted.")

            if access_token:
                AccessToken(access_token).blacklist()
                logger.info("Access token blacklisted.")

            response = Response({"message": "Logged out successfully."}, status=200)
            response.delete_cookie("refresh_token")
            response.delete_cookie("access_token")

            user = request.user
            if hasattr(user, "socialauth_google"):
                try:
                    revoke_google_token(user.socialauth_google.token)
                    revoke_google_token(user.socialauth_google.refresh_token)
                    logger.info("Google OAuth tokens revoked.")
                except Exception as e:
                    logger.error(f"Failed to revoke Google tokens: {str(e)}")
                    return Response({"error": "Failed to revoke Google tokens."}, status=500)

            return response

        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return Response({"error": "Error during logout."}, status=500)


def revoke_google_token(token):
    url = "https://oauth2.googleapis.com/revoke"
    response = requests.post(url, data={"token": token})
    if response.status_code != 200:
        raise Exception("Failed to revoke token.")


class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Profile.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        if Profile.objects.filter(user=self.request.user).exists():
            raise ValidationError({"detail": "Profile already exists for this user."})
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, *args, **kwargs)
            return Response({
                "message": "Profile created successfully.",
                "data": response.data
            }, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Profile creation failed: {str(e)}"}, status=400)

    def update(self, request, *args, **kwargs):
        try:
            response = super().update(request, *args, **kwargs)
            return Response({
                "message": "Profile updated successfully.",
                "data": response.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"Profile update failed: {str(e)}"}, status=400)
