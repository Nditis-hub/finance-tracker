from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Role, User


class SignUpForm(UserCreationForm):
    """Public sign-up always creates a Staff user. Admins promote users from the Users page."""

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")


class UserAdminForm(forms.ModelForm):
    """Lets an admin change someone's role or switch their account on or off."""

    class Meta:
        model = User
        fields = ("role", "is_active")
        labels = {"is_active": "Account active (can log in)"}

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user

    def clean(self):
        cleaned = super().clean()
        # An admin cannot lock themselves out, so there is always at least one working admin.
        if self.acting_user is not None and self.instance.pk == self.acting_user.pk:
            if cleaned.get("role") != Role.ADMIN:
                self.add_error("role", "You cannot remove your own admin role.")
            if cleaned.get("is_active") is False:
                self.add_error("is_active", "You cannot deactivate your own account.")
        return cleaned