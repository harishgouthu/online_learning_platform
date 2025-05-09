import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from allauth.exceptions import ImmediateHttpResponse
from django.http import JsonResponse
from allauth.account.utils import perform_login
from django.contrib import messages

User = get_user_model()
logger = logging.getLogger(__name__)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Enhanced adapter with better handling for both social and regular users
    """

    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a
        social provider, but before the login is actually processed.
        """
        # Ignore existing social accounts
        if sociallogin.is_existing:
            return

        # Check for an existing user with the same email
        email = sociallogin.user.email
        if not email:
            logger.warning("No email provided by the social account provider.")
            return

        try:
            user = User.objects.get(email=email)
            logger.info(f"Found existing user {email}")

            # Check if this is a regular user (has password)
            if user.has_usable_password():
                logger.info(f"User {email} is a regular user, connecting social account")
                # Connect the social account to the existing user
                sociallogin.connect(request, user)
            else:
                logger.info(f"User {email} is already a social user")

        except User.DoesNotExist:
            logger.info(f"No existing user found for {email}, allowing new signup")
            # Continue with normal social signup flow

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social login user.
        """
        user = super().save_user(request, sociallogin, form)

        # Set unusable password explicitly for social users
        user.set_unusable_password()
        user.save()

        logger.info(f"Social user {user.email} created successfully")
        return user

    def authentication_error(self, request, provider_id, error=None, exception=None, extra_context=None):
        """
        Handle authentication errors gracefully.
        """
        logger.error(
            f"Social authentication error with {provider_id}: {error}",
            exc_info=exception
        )
        return JsonResponse(
            {"error": "Social authentication failed"},
            status=400
        )