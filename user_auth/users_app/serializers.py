

from django.contrib.auth import get_user_model, authenticate
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from dj_rest_auth.registration.serializers import RegisterSerializer, SocialLoginSerializer
from allauth.account.adapter import get_adapter
from allauth.account.utils import setup_user_email
from rest_framework.exceptions import AuthenticationFailed
from .models import Profile
from allauth.socialaccount.models import SocialAccount
User = get_user_model()


class CustomRegisterSerializer(RegisterSerializer):
    username = None
    email = serializers.EmailField(required=True)
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email is already registered.")
        return value

    def validate(self, data):
        if data["password1"] != data["password2"]:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def save(self, request):
        adapter = get_adapter()
        user = adapter.new_user(request)
        self.cleaned_data = self.get_cleaned_data()
        adapter.save_user(request, user, self)
        setup_user_email(request, user, [])
        return user





class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        return token

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise AuthenticationFailed("incorrect email.")

        if not user.check_password(password):
            raise AuthenticationFailed("incorrect password.")

        if not user.is_active:
            raise AuthenticationFailed("User account is disabled.")

        data = super().validate(attrs)
        data["user"] = {
            "id": self.user.id,
            "email": self.user.email,
        }
        data["message"] = "Login successful"
        return data







class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username")

    class Meta:
        model = Profile
        fields = ["id", "username", "first_name", "last_name", "bio", "profile_image"]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        username = user_data.get("username")

        if username:
            instance.user.username = username
            instance.user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance
