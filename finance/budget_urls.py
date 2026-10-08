from django.urls import path

from . import views

urlpatterns = [
    path("", views.BudgetListView.as_view(), name="budget_list"),
    path("new/", views.BudgetCreateView.as_view(), name="budget_create"),
    path("history/<int:department_id>/", views.BudgetHistoryView.as_view(), name="budget_history"),
]