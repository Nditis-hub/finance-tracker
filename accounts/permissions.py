from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .models import Role


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict a class-based view to the roles listed in `allowed_roles`."""

    allowed_roles = ()

    def test_func(self):
        return self.request.user.role in self.allowed_roles


class FinanceManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.ADMIN, Role.FINANCE_MANAGER)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.ADMIN,)