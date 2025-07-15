from django.core.management.base import BaseCommand
from user_auth.models import CustomUser
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

# print("✅ Custom createsuperuser command from user_auth loaded.")

class Command(BaseCommand):
    help = 'Create a superuser with email and username (with duplicate checks).'

    def handle(self, *args, **kwargs):
        while True:
            email = input("Email: ").strip()
            if not email:
                self.stderr.write("Email cannot be blank.")
                continue
            if CustomUser.objects.filter(email=email).exists():
                self.stderr.write("❌ Email already exists. Try another.")
                continue
            break

        while True:
            username = input("Username: ").strip()
            if not username:
                self.stderr.write("Username cannot be blank.")
                continue
            if CustomUser.objects.filter(username=username).exists():
                self.stderr.write("❌ Username already exists. Try another.")
                continue
            break

        while True:
            password = input("Password: ").strip()
            password2 = input("Password (again): ").strip()
            if password != password2:
                self.stderr.write("❌ Passwords do not match.")
                continue
            try:
                validate_password(password)
                break
            except ValidationError as e:
                for error in e:
                    self.stderr.write(f"❌ {error}")
                choice = input("Bypass password validation and create user anyway? [y/N]: ").lower()
                if choice == 'y':
                    break

        user = CustomUser.objects.create_superuser(
            email=email,
            username=username,
            password=password
        )

        self.stdout.write(self.style.SUCCESS(f"✅ Superuser created: {user.email}"))
