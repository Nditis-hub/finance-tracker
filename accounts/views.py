from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView

from .forms import ProfileForm, SignUpForm, UserAdminForm
from .models import User
from .permissions import AdminRequiredMixin


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()  # role defaults to Staff; it is never taken from the form
        messages.success(request, "Account created. You can now log in.")
        return redirect("login")
    return render(request, "registration/signup.html", {"form": form})


class ProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("profile")
    success_message = "Profile updated."

    def get_object(self, queryset=None):
        return self.request.user


class ChangePasswordView(LoginRequiredMixin, SuccessMessageMixin, PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("profile")
    success_message = "Password changed."


class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    paginate_by = 20
    context_object_name = "users"
    ordering = ["username"]


class UserUpdateView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserAdminForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("user_list")
    success_message = "User updated."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["acting_user"] = self.request.user
        return kwargs