
from rest_framework import status, viewsets, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

from dj_rest_auth.registration.views import RegisterView, SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from rest_framework.response import Response
from rest_framework import status
from .models import Profile,OTP
from .serializers import (
    CustomRegisterSerializer,
    CustomTokenObtainPairSerializer,
    ProfileSerializer,
)

import logging
import requests

logger = logging.getLogger(__name__)


# class CustomRegisterView(RegisterView):
#     serializer_class = CustomRegisterSerializer
#
#     def get_response_data(self, user):
#         return {"message": "Registered successfully"}

class CustomRegisterView(RegisterView):
    serializer_class = CustomRegisterSerializer

    def get_response_data(self, user):
        otp_obj = OTP.objects.get(user=user)
        return {
            "message": "Registered successfully. Please verify OTP.",
            "otp_token": str(otp_obj.token)
        }

class OTPVerifyView(APIView):
    def post(self, request):
        token = request.data.get("otp_token")
        code = request.data.get("otp")

        if not token or not code:
            return Response({"error": "OTP token and code are required."}, status=400)

        otp_obj = OTP.objects.filter(token=token, code=code).first()

        if not otp_obj or otp_obj.is_expired():
            return Response({"error": "Invalid or expired OTP."}, status=400)

        otp_obj.is_verified = True
        otp_obj.save()

        user = otp_obj.user
        user.is_active = True
        user.save()

        return Response({"message": "Account verified successfully."}, status=200)

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
import razorpay
from django.conf import settings
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import SubscriptionPlan, UserSubscription


class CreateSubscriptionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        plan_id = request.data.get("plan_id")

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({"success": False, "message": "Plan not found."}, status=404)

        amount_paise = int(plan.price * 100)  # Razorpay expects paise

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        # Create order
        razorpay_order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": "1"
        })

        return Response({
            "success": True,
            "order_id": razorpay_order['id'],
            "razorpay_key": settings.RAZORPAY_KEY_ID,
            "amount": amount_paise,
            "currency": "INR",
            "plan_name": plan.get_name_display(),
            "plan_id": plan.id
        })

class VerifyPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        user = request.user

        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")
        plan_id = data.get("plan_id")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response({"success": False, "message": "Missing payment details."}, status=400)

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        try:
            client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature
            })
        except razorpay.errors.SignatureVerificationError:
            return Response({"success": False, "message": "Invalid payment signature."}, status=400)

        # Create/Update Subscription
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({"success": False, "message": "Plan not found."}, status=404)

        start = timezone.now()
        end = start + timezone.timedelta(days=plan.duration_days)

        subscription, _ = UserSubscription.objects.update_or_create(
            user=user,
            defaults={
                "plan": plan,
                "start_date": start,
                "end_date": end,
                "is_active": True
            }
        )

        return Response({
            "success": True,
            "message": "Payment successful and subscription activated.",
            "plan": plan.get_name_display(),
            "valid_till": end
        }, status=200)
