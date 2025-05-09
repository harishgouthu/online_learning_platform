from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email


    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"



class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
