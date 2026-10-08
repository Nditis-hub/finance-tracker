from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    ADMIN = "admin", "Admin"
    FINANCE_MANAGER = "finance_manager", "Finance Manager"
    STAFF = "staff", "Staff"


class HotelUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """User with a hotel role. Only admins can change roles."""

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    email = models.EmailField("email address", unique=True)

    objects = HotelUserManager()

    @property
    def is_hotel_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_finance_manager(self):
        return self.role == Role.FINANCE_MANAGER

    @property
    def can_manage_finance(self):
        """Admins and finance managers can approve transactions and set budgets."""
        return self.role in (Role.ADMIN, Role.FINANCE_MANAGER)

    def __str__(self):
        return self.get_full_name() or self.username