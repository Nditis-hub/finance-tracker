from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from accounts.permissions import FinanceManagerRequiredMixin

from .models import Supplier, SupplierInvoice, Transaction
from .payables import payables_summary, record_payment
from .payables_forms import InvoiceForm, PaymentForm


class InvoiceListView(FinanceManagerRequiredMixin, ListView):
    model = SupplierInvoice
    template_name = "finance/payables_list.html"
    paginate_by = 20
    context_object_name = "invoices"
    STATUSES = [("open", "Still owed"), ("overdue", "Overdue"), ("paid", "Paid"), ("all", "All")]

    def get_queryset(self):
        qs = SupplierInvoice.objects.with_balance().select_related("supplier", "department")
        self.status = self.request.GET.get("status", "open")
        if self.status not in dict(self.STATUSES):
            self.status = "open"
        today = timezone.localdate()
        if self.status == "open":
            qs = qs.filter(balance_due__gt=0)
        elif self.status == "overdue":
            qs = qs.filter(balance_due__gt=0, due_date__lt=today)
        elif self.status == "paid":
            qs = qs.filter(balance_due__lte=0)
        supplier = self.request.GET.get("supplier", "")
        self.supplier_id = int(supplier) if supplier.isdigit() else None
        if self.supplier_id:
            qs = qs.filter(supplier_id=self.supplier_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(payables_summary())
        ctx["status"] = self.status
        ctx["statuses"] = self.STATUSES
        ctx["suppliers"] = Supplier.objects.all()
        ctx["supplier_id"] = self.supplier_id
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["query_string"] = params.urlencode()
        return ctx


class InvoiceCreateView(FinanceManagerRequiredMixin, CreateView):
    model = SupplierInvoice
    form_class = InvoiceForm
    template_name = "finance/payables_form.html"

    def get_initial(self):
        initial = super().get_initial()
        supplier = self.request.GET.get("supplier", "")
        if supplier.isdigit():
            initial["supplier"] = supplier
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Invoice added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("invoice_detail", args=[self.object.pk])


class InvoiceDetailView(FinanceManagerRequiredMixin, DetailView):
    model = SupplierInvoice
    template_name = "finance/payables_detail.html"
    context_object_name = "invoice"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["payments"] = self.object.payments.select_related("created_by", "approved_by").order_by("-date", "-id")
        return ctx


class InvoiceUpdateView(FinanceManagerRequiredMixin, UpdateView):
    model = SupplierInvoice
    form_class = InvoiceForm
    template_name = "finance/payables_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Invoice updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("invoice_detail", args=[self.object.pk])


class InvoicePayView(FinanceManagerRequiredMixin, FormView):
    form_class = PaymentForm
    template_name = "finance/payables_pay.html"

    def dispatch(self, request, *args, **kwargs):
        self.invoice = get_object_or_404(SupplierInvoice, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if self.invoice.balance <= 0:
            messages.info(request, "That invoice is already fully paid.")
            return redirect("invoice_detail", pk=self.invoice.pk)
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["invoice"] = self.invoice
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invoice"] = self.invoice
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            payment = record_payment(
                self.invoice, self.request.user, data["amount"], data["date"],
                data["payment_method"], data["payment_reference"],
            )
        except ValueError as error:
            form.add_error("amount", str(error))
            return self.form_invalid(form)
        if payment.status == Transaction.Status.APPROVED:
            messages.success(self.request, "Payment recorded and added to the expenses.")
        else:
            messages.warning(self.request, "Payment recorded. It is above the approval limit, so an admin must approve the expense.")
        return redirect("invoice_detail", pk=self.invoice.pk)


class InvoiceDeleteView(FinanceManagerRequiredMixin, View):
    """POST-only. An invoice with payments against it cannot be deleted."""

    http_method_names = ["post"]

    def post(self, request, pk):
        invoice = get_object_or_404(SupplierInvoice, pk=pk)
        if invoice.payments.exists():
            messages.error(request, "This invoice has payments recorded against it, so it cannot be deleted.")
            return redirect("invoice_detail", pk=invoice.pk)
        invoice.delete()
        messages.success(request, f"Invoice {invoice.invoice_number} deleted.")
        return redirect("invoice_list")


class SupplierStatementView(FinanceManagerRequiredMixin, TemplateView):
    template_name = "finance/payables_supplier.html"

    def get_context_data(self, pk, **kwargs):
        ctx = super().get_context_data(**kwargs)
        supplier = get_object_or_404(Supplier, pk=pk)
        invoices = list(SupplierInvoice.objects.with_balance().filter(supplier=supplier).order_by("-invoice_date", "-id"))
        ctx.update(
            supplier=supplier, invoices=invoices,
            billed_total=sum((i.amount for i in invoices), Decimal("0.00")),
            paid_total=sum((i.paid_total for i in invoices), Decimal("0.00")),
            owed_total=sum((i.balance_due for i in invoices if i.balance_due > 0), Decimal("0.00")),
        )
        return ctx