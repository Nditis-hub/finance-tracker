from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("transactions/", include("finance.urls")),
    path("budgets/", include("finance.budget_urls")),
    path("bookings/", include("finance.booking_urls")),
    path("suppliers/", include("finance.supplier_urls")),
    path("recurring/", include("finance.recurring_urls")),
    path("audit-log/", include("audit.urls")),
    path("", include("core.urls")),
]