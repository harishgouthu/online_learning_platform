from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_premium(self):
        subscription = getattr(self, 'usersubscription', None)
        return bool(subscription and subscription.has_active_subscription())


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
# models.py
import uuid
from django.utils import timezone
from datetime import timedelta

class OTP(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def generate_otp(self):
        import random
        self.code = str(random.randint(100000, 999999))
        self.token = uuid.uuid4()
        self.created_at = timezone.now()
        self.is_verified = False
        self.save()

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=10)


class SubscriptionPlan(models.Model):
    PLAN_CHOICES = [
        ('monthly', '1 Month'),
        ('half_yearly', '6 Months'),
        ('yearly', 'Annual'),
    ]

    name = models.CharField(max_length=50, choices=PLAN_CHOICES, unique=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    duration_days = models.PositiveIntegerField()
    # max_questions_per_day = models.PositiveIntegerField(default=100)
    # max_image_uploads = models.PositiveIntegerField(default=100)

    class Meta:
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"

    def __str__(self):
        return f"{self.get_name_display()} - ₹{self.price}"



class UserSubscription(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "User Subscription"
        verbose_name_plural = "User Subscriptions"

    def save(self, *args, **kwargs):
        if not self.end_date and self.plan:
            self.end_date = self.start_date + timezone.timedelta(days=self.plan.duration_days)
        # Auto-disable if expired
        if self.end_date and self.end_date < timezone.now():
            self.is_active = False
        super().save(*args, **kwargs)

    def has_active_subscription(self):
        return self.is_active and self.end_date >= timezone.now()

    def remaining_days(self):
        if self.has_active_subscription():
            return (self.end_date - timezone.now()).days
        return 0

    def __str__(self):
        return f"{self.user.email} - {self.plan.name if self.plan else 'No Plan'}"

