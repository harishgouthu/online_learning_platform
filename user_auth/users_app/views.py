
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import RegisterView, SocialLoginView
from rest_framework_simplejwt.views import TokenObtainPairView

from rest_framework import status
from rest_framework import viewsets, permissions
from .models import Profile
from .serializers import ProfileSerializer
from .serializers import (
    CustomRegisterSerializer,
    CustomTokenObtainPairSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework.views import APIView
from rest_framework.response import Response
import logging
import requests
from rest_framework.exceptions import ValidationError
logger = logging.getLogger(__name__)



class CustomRegisterView(RegisterView):
    serializer_class = CustomRegisterSerializer

    def get_response_data(self, user):
        return {
            "message": "Registered successfully"
        }


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter





class LogoutView(APIView):
    def post(self, request):
        # Step 1: Clear JWT tokens (access token and refresh token) for regular users
        try:
            # Blacklist the refresh token (if applicable)
            refresh_token = request.COOKIES.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()  # If you're using token blacklisting
                logger.info(f"Refresh token blacklisted: {refresh_token}")

            # Blacklist the access token (if applicable)
            access_token = request.COOKIES.get('access_token')
            if access_token:
                token = AccessToken(access_token)
                token.blacklist()  # If you're using token blacklisting
                logger.info(f"Access token blacklisted: {access_token}")

            # Clear JWT tokens from cookies
            response = Response({"message": "Logged out successfully."})
            response.delete_cookie('access_token')
            response.delete_cookie('refresh_token')

            logger.info("JWT tokens deleted from cookies.")

        except Exception as e:
            logger.error(f"Error during token blacklisting or deletion: {e}")
            return Response({"error": "Error logging out. Please try again."}, status=500)

        # Step 2: Revoke Google OAuth tokens if the user logged in via Google OAuth
        user = request.user
        if hasattr(user, 'socialauth_google'):  # Check if the user has a Google social account
            google_token = user.socialauth_google.token
            google_refresh_token = user.socialauth_google.refresh_token

            # Revoke Google OAuth access token and refresh token
            try:
                revoke_google_token(google_token)  # Revoke access token
                revoke_google_token(google_refresh_token)  # Revoke refresh token
                logger.info("Google OAuth tokens revoked successfully.")
            except Exception as e:
                logger.error(f"Failed to revoke Google OAuth tokens: {e}")
                return Response({"error": "Failed to revoke Google OAuth tokens. Please try again."}, status=500)

        return response


# Helper function to revoke Google OAuth token
def revoke_google_token(token):
    url = "https://oauth2.googleapis.com/revoke"
    params = {'token': token}
    response = requests.post(url, data=params)

    if response.status_code == 200:
        logger.info(f"Google OAuth token revoked successfully: {token}")
    else:
        logger.error(f"Failed to revoke Google OAuth token: {token} - Status Code: {response.status_code}")
        raise Exception(f"Failed to revoke token: {response.status_code}")


class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Return the profile(s) associated with the authenticated user
        return Profile.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        if Profile.objects.filter(user=self.request.user).exists():
            raise ValidationError("Profile already exists for this user.")
        serializer.save(user=self.request.user)
