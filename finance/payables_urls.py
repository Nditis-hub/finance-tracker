from django.urls import path

from . import payables_views as views

urlpatterns = [
    path("", views.InvoiceListView.as_view(), name="invoice_list"),
    path("new/", views.InvoiceCreateView.as_view(), name="invoice_create"),
    path("supplier/<int:pk>/", views.SupplierStatementView.as_view(), name="supplier_statement"),
    path("<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("<int:pk>/edit/", views.InvoiceUpdateView.as_view(), name="invoice_edit"),
    path("<int:pk>/pay/", views.InvoicePayView.as_view(), name="invoice_pay"),
    path("<int:pk>/delete/", views.InvoiceDeleteView.as_view(), name="invoice_delete"),
]