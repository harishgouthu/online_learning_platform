
from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from dj_rest_auth.registration.serializers import (
    RegisterSerializer,
    SocialLoginSerializer,
)



from django.contrib.auth import get_user_model
from rest_framework import serializers
from allauth.account.adapter import get_adapter
from allauth.account.utils import setup_user_email

User = get_user_model()

class CustomRegisterSerializer(RegisterSerializer):
    username = None  # Remove username
    email = serializers.EmailField(required=True)
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("User with this email is already registered.")
        return value

    def validate(self, data):
        if data['password1'] != data['password2']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def save(self, request):
        adapter = get_adapter()
        user = adapter.new_user(request)
        self.cleaned_data = self.get_cleaned_data()
        adapter.save_user(request, user, self)
        setup_user_email(request, user, [])
        return user


class CustomLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email or not password:
            raise AuthenticationFailed("Email and password are required.")

        user = authenticate(self.context['request'], email=email, password=password)

        if user is None:
            raise AuthenticationFailed("Invalid email or password.")

        attrs['user'] = user
        return attrs

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'email': self.user.email,
        }
        return data

class CustomSocialLoginSerializer(SocialLoginSerializer):
    def validate(self, attrs):
        validated_data = super().validate(attrs)
        refresh = RefreshToken.for_user(self.user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


from .models import Profile

class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username')

    class Meta:
        model = Profile
        fields = ['id', 'username', 'first_name', 'last_name', 'bio', 'profile_image']

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        username = user_data.get('username')

        if username:
            instance.user.username = username
            instance.user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance
