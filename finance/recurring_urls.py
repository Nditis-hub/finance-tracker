from django.urls import path

from . import views

urlpatterns = [
    path("", views.RecurringListView.as_view(), name="recurring_list"),
    path("new/", views.RecurringCreateView.as_view(), name="recurring_create"),
    path("generate/", views.RecurringGenerateView.as_view(), name="recurring_generate"),
    path("<int:pk>/edit/", views.RecurringUpdateView.as_view(), name="recurring_edit"),
    path("<int:pk>/toggle/", views.RecurringToggleView.as_view(), name="recurring_toggle"),
    path("<int:pk>/delete/", views.RecurringDeleteView.as_view(), name="recurring_delete"),
]