from django.urls import path

from . import views

urlpatterns = [
    path("", views.TransactionListView.as_view(), name="transaction_list"),
    path("new/", views.TransactionCreateView.as_view(), name="transaction_create"),
    path("export/", views.TransactionExportView.as_view(), name="transaction_export"),
    path("<int:pk>/edit/", views.TransactionUpdateView.as_view(), name="transaction_edit"),
    path("<int:pk>/delete/", views.TransactionDeleteView.as_view(), name="transaction_delete"),
    path("<int:pk>/void/", views.TransactionVoidView.as_view(), name="transaction_void"),
    path("<int:pk>/approve/", views.TransactionApproveView.as_view(), name="transaction_approve"),
    path("<int:pk>/reject/", views.TransactionRejectView.as_view(), name="transaction_reject"),
]