from django.shortcuts import redirect
from django.urls import path

from . import views

urlpatterns = [
    path("", lambda request: redirect("dashboard"), name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("analytics/", views.AnalyticsView.as_view(), name="analytics"),
    path("reports/profit-loss/", views.ProfitLossView.as_view(), name="profit_loss"),
    path("reports/profit-loss/export/", views.ProfitLossExportView.as_view(), name="profit_loss_export"),
    path("departments/", views.DepartmentListView.as_view(), name="department_list"),
    path("departments/new/", views.DepartmentCreateView.as_view(), name="department_create"),
    path("departments/<int:pk>/edit/", views.DepartmentUpdateView.as_view(), name="department_edit"),
    path("departments/<int:pk>/delete/", views.DepartmentDeleteView.as_view(), name="department_delete"),
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),
]