# from django.urls import path
# from .views import CustomRegisterView, CustomTokenObtainPairView, GoogleLogin
# from rest_framework_simplejwt.views import TokenVerifyView
#
# urlpatterns = [
#     path('login/', CustomTokenObtainPairView.as_view(), name='custom_login'),
#     path('register/', CustomRegisterView.as_view(), name='custom_register'),
#     path('google/login/', GoogleLogin.as_view(), name='google_login'),
#     path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
# ]
#
#

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProfileViewSet,
    CustomRegisterView,
    CustomTokenObtainPairView,
    GoogleLogin,
    LogoutView,
    OTPVerifyView
)
from rest_framework_simplejwt.views import TokenVerifyView

# Initialize the router and register the ProfileViewSet
router = DefaultRouter()
router.register(r'profile', ProfileViewSet, basename='profile')

# Define the URL patterns
urlpatterns = [
    # Include the router-generated URLs
    path('', include(router.urls)),

    # Authentication endpoints
    path('login/', CustomTokenObtainPairView.as_view(), name='custom_login'),
    path('register/', CustomRegisterView.as_view(), name='custom_register'),
    path('google/login/', GoogleLogin.as_view(), name='google_login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('verify-otp/', OTPVerifyView.as_view(), name='verify-otp'),
]
