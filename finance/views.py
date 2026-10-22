import csv
import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction as db_transaction
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from accounts.permissions import FinanceManagerRequiredMixin
from core.models import Category, Department

from .forms import (BookingEditForm, BookingForm, BudgetForm, RecurringExpenseForm, SupplierForm,
                    TransactionFilterForm, TransactionForm)
from .models import Booking, Budget, RecurringExpense, Supplier, Transaction
from .recurring import generate_due_expenses, pending_count


class TransactionListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = "finance/transaction_list.html"
    paginate_by = 20
    context_object_name = "transactions"

    def get_queryset(self):
        qs = Transaction.objects.select_related("category", "department", "created_by", "approved_by")
        user = self.request.user
        if not user.can_manage_finance:
            qs = qs.filter(created_by=user)  # staff only see what they recorded
        self.filter_form = TransactionFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            f = self.filter_form.cleaned_data
            if f["status"]:
                qs = qs.filter(status=f["status"])
            if f["type"]:
                qs = qs.filter(type=f["type"])
            if f["department"]:
                qs = qs.filter(department=f["department"])
            if f["date_from"]:
                qs = qs.filter(date__gte=f["date_from"])
            if f["date_to"]:
                qs = qs.filter(date__lte=f["date_to"])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_form"] = self.filter_form
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["query_string"] = params.urlencode()
        user = self.request.user
        for t in ctx["transactions"]:
            t.can_modify = t.user_can_modify(user)
            pending = t.status == Transaction.Status.PENDING
            t.can_approve = pending and t.user_can_approve(user)
            t.needs_admin = pending and t.requires_admin_approval
        return ctx


def _csv_safe(value):
    """Stop spreadsheet programs from running text that starts like a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


class TransactionExportView(TransactionListView):
    """Download the transactions the user can see, with the same filters as the list page."""

    def get(self, request, *args, **kwargs):
        qs = self.get_queryset().select_related("supplier", "booking")
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="transactions-{timezone.localdate():%Y-%m-%d}.csv"'
        response.write("\ufeff")  # lets Excel read the file as UTF-8
        writer = csv.writer(response)
        writer.writerow(["Date", "Type", "Category", "Department", "Amount", "Description",
                         "Supplier", "Booking", "Status", "Recorded by", "Approved by", "Payment method", "Payment reference", "Rejection reason"])
        for t in qs.iterator():
            writer.writerow([
                t.date.isoformat(), t.get_type_display(), _csv_safe(t.category.name), _csv_safe(t.department.name),
                t.amount, _csv_safe(t.description), _csv_safe(t.supplier.name if t.supplier else ""),
                _csv_safe(t.booking.guest_name if t.booking else ""), t.get_status_display(),
                _csv_safe(t.created_by), _csv_safe(t.approved_by),
                t.get_payment_method_display(), _csv_safe(t.payment_reference), _csv_safe(t.rejection_reason),
            ])
        return response


class _TransactionFormMixin:
    model = Transaction
    form_class = TransactionForm
    template_name = "finance/transaction_form.html"
    success_url = reverse_lazy("transaction_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["category_kinds"] = json.dumps({str(c.pk): c.kind for c in Category.objects.all()})
        return ctx


class TransactionCreateView(_TransactionFormMixin, LoginRequiredMixin, CreateView):
    def form_valid(self, form):
        user = self.request.user
        form.instance.created_by = user
        if user.can_manage_finance and form.instance.user_can_approve(user):
            # Admins and finance managers don't need a second person to approve their own entries.
            form.instance.status = Transaction.Status.APPROVED
            form.instance.approved_by = user
            messages.success(self.request, "Transaction recorded and approved.")
        elif user.can_manage_finance:
            messages.warning(self.request, "Transaction recorded. It is above the approval limit, so an admin must approve it.")
        else:
            messages.success(self.request, "Transaction submitted for approval.")
        return super().form_valid(form)


class TransactionUpdateView(_TransactionFormMixin, LoginRequiredMixin, UpdateView):
    """Edit a pending or rejected transaction. Editing a rejected one sends it back for approval."""

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not obj.user_can_modify(self.request.user):
            raise PermissionDenied
        return obj

    def form_valid(self, form):
        if form.instance.status == Transaction.Status.REJECTED:
            form.instance.status = Transaction.Status.PENDING
            form.instance.approved_by = None
            form.instance.rejection_reason = ""
            messages.success(self.request, "Transaction updated and resubmitted for approval.")
        else:
            messages.success(self.request, "Transaction updated.")
        return super().form_valid(form)


class TransactionDeleteView(LoginRequiredMixin, View):
    """POST-only. Pending and rejected transactions can be deleted; the audit log keeps a record."""

    http_method_names = ["post"]

    def post(self, request, pk):
        transaction = get_object_or_404(Transaction, pk=pk)
        if not transaction.user_can_modify(request.user):
            raise PermissionDenied
        transaction.delete()
        messages.success(request, "Transaction deleted.")
        return redirect(request.POST.get("next") or "transaction_list")


class TransactionVoidView(FinanceManagerRequiredMixin, View):
    """POST-only. An approved transaction that was wrong is voided, not deleted."""

    http_method_names = ["post"]

    def post(self, request, pk):
        transaction = get_object_or_404(Transaction, pk=pk)
        if transaction.status != Transaction.Status.APPROVED:
            messages.warning(request, "Only approved transactions can be voided.")
        else:
            transaction.void(request.user)
            messages.success(request, "Transaction voided. It no longer counts toward budgets or reports.")
        return redirect(request.POST.get("next") or "transaction_list")


class _DecisionView(FinanceManagerRequiredMixin, View):
    """POST-only: approve or reject a pending transaction."""

    http_method_names = ["post"]

    def post(self, request, pk):
        transaction = get_object_or_404(Transaction, pk=pk)
        if transaction.status != Transaction.Status.PENDING:
            messages.warning(request, "That transaction has already been decided.")
        else:
            self.decide(transaction, request.user)
        return redirect(request.POST.get("next") or "transaction_list")


class TransactionApproveView(_DecisionView):
    def decide(self, transaction, user):
        try:
            transaction.approve(user)
        except PermissionError:
            messages.error(self.request, "This expense is above the approval limit, so only an admin can approve it.")
        else:
            messages.success(self.request, "Transaction approved.")


class TransactionRejectView(_DecisionView):
    def decide(self, transaction, user):
        reason = self.request.POST.get("reason", "").strip()
        if not reason:
            messages.error(self.request, "Please give a reason for rejecting the transaction.")
            return
        transaction.reject(user, reason)
        messages.success(self.request, "Transaction rejected.")


# ---------- Budgets (admins and finance managers only) ----------

class BudgetListView(FinanceManagerRequiredMixin, TemplateView):
    template_name = "finance/budget_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        budgets = list(Budget.objects.filter(is_current=True).select_related("department"))
        with_budget = {b.department_id for b in budgets}
        ctx["budgets"] = budgets
        ctx["departments_without_budget"] = Department.objects.exclude(pk__in=with_budget)
        return ctx


class BudgetCreateView(FinanceManagerRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = "finance/budget_form.html"
    success_url = reverse_lazy("budget_list")

    def get_initial(self):
        initial = super().get_initial()
        dept = self.request.GET.get("department")
        if dept and dept.isdigit():
            initial["department"] = dept
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        had_previous = Budget.objects.filter(department=form.cleaned_data["department"], is_current=True).exists()
        response = super().form_valid(form)
        if had_previous:
            messages.success(self.request, "New budget version saved. The previous one is kept in the history.")
        else:
            messages.success(self.request, "Budget saved.")
        return response


class BudgetHistoryView(FinanceManagerRequiredMixin, TemplateView):
    template_name = "finance/budget_history.html"

    def get_context_data(self, department_id, **kwargs):
        ctx = super().get_context_data(**kwargs)
        department = get_object_or_404(Department, pk=department_id)
        ctx["department"] = department
        ctx["versions"] = Budget.objects.filter(department=department).order_by("-created_at").select_related("created_by")
        return ctx


# ---------- Bookings ----------

class BookingListView(LoginRequiredMixin, ListView):
    model = Booking
    template_name = "finance/booking_list.html"
    paginate_by = 20
    context_object_name = "bookings"

    def get_queryset(self):
        qs = Booking.objects.select_related("department")
        status = self.request.GET.get("status")
        if status in Booking.Status.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["status_choices"] = Booking.Status.choices
        ctx["selected_status"] = self.request.GET.get("status", "")
        ctx["update_choices"] = [
            c for c in Booking.Status.choices if user.can_manage_finance or c[0] != Booking.Status.PAID
        ]
        return ctx


class BookingCreateView(LoginRequiredMixin, CreateView):
    model = Booking
    form_class = BookingForm
    template_name = "finance/booking_form.html"
    success_url = reverse_lazy("booking_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        with db_transaction.atomic():
            response = super().form_valid(form)
            if self.object.status == Booking.Status.PAID:
                self.object.record_payment(self.request.user)
        messages.success(self.request, "Booking added.")
        return response


class BookingUpdateView(LoginRequiredMixin, UpdateView):
    """Edit a booking's details. Paid bookings are locked because their income is already recorded."""

    model = Booking
    form_class = BookingEditForm
    template_name = "finance/booking_form.html"
    success_url = reverse_lazy("booking_list")

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not obj.is_editable:
            raise PermissionDenied
        return obj

    def form_valid(self, form):
        messages.success(self.request, "Booking updated.")
        return super().form_valid(form)


class BookingStatusView(LoginRequiredMixin, View):
    """POST-only: change a booking's status. Marking it paid records the income."""

    http_method_names = ["post"]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        new_status = request.POST.get("status")
        if new_status not in Booking.Status.values:
            messages.error(request, "That status is not valid.")
        elif new_status == Booking.Status.PAID and not request.user.can_manage_finance:
            messages.error(request, "Only a finance manager or admin can mark a booking as paid.")
        else:
            with db_transaction.atomic():
                booking.status = new_status
                booking.save(update_fields=["status"])
                if new_status == Booking.Status.PAID:
                    if booking.record_payment(request.user):
                        messages.success(request, "Booking marked as paid and income recorded.")
                    else:
                        messages.info(request, "Booking marked as paid (income was already recorded).")
                else:
                    messages.success(request, "Booking status updated.")
        return redirect("booking_list")


# ---------- Suppliers (admins and finance managers only) ----------

class SupplierListView(FinanceManagerRequiredMixin, ListView):
    model = Supplier
    template_name = "finance/supplier_list.html"
    paginate_by = 20
    context_object_name = "suppliers"


class SupplierCreateView(FinanceManagerRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "finance/supplier_form.html"
    success_url = reverse_lazy("supplier_list")

    def form_valid(self, form):
        messages.success(self.request, "Supplier added.")
        return super().form_valid(form)


class SupplierUpdateView(FinanceManagerRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "finance/supplier_form.html"
    success_url = reverse_lazy("supplier_list")

    def form_valid(self, form):
        messages.success(self.request, "Supplier updated.")
        return super().form_valid(form)

class SupplierDeleteView(FinanceManagerRequiredMixin, View):
    """POST-only. A supplier that appears on transactions cannot be deleted, so history stays intact."""

    http_method_names = ["post"]

    def post(self, request, pk):
        supplier = get_object_or_404(Supplier, pk=pk)
        used = supplier.transactions.count()
        invoices = supplier.invoices.count()
        if used:
            messages.error(request, f'"{supplier.name}" is on {used} transaction{"s" if used != 1 else ""}, so it cannot be deleted.')
        elif invoices:
            messages.error(request, f'"{supplier.name}" has {invoices} invoice{"s" if invoices != 1 else ""}, so it cannot be deleted.')
        else:
            supplier.delete()
            messages.success(request, f'Supplier "{supplier.name}" deleted.')
        return redirect("supplier_list")


class RecurringListView(FinanceManagerRequiredMixin, ListView):
    model = RecurringExpense
    template_name = "finance/recurring_list.html"
    context_object_name = "items"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        for item in ctx["items"]:
            item.next_due_date = item.next_due()
            item.due_now = item.is_active and bool(item.due_dates(today))
        ctx["pending_count"] = pending_count(today)
        return ctx


class RecurringCreateView(FinanceManagerRequiredMixin, CreateView):
    model = RecurringExpense
    form_class = RecurringExpenseForm
    template_name = "finance/recurring_form.html"
    success_url = reverse_lazy("recurring_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Recurring expense added.")
        return super().form_valid(form)


class RecurringUpdateView(FinanceManagerRequiredMixin, UpdateView):
    model = RecurringExpense
    form_class = RecurringExpenseForm
    template_name = "finance/recurring_form.html"
    success_url = reverse_lazy("recurring_list")

    def form_valid(self, form):
        messages.success(self.request, "Recurring expense updated.")
        return super().form_valid(form)


class RecurringToggleView(FinanceManagerRequiredMixin, View):
    """POST-only. Pause or resume a recurring expense. Months missed while paused are skipped."""

    http_method_names = ["post"]

    def post(self, request, pk):
        item = get_object_or_404(RecurringExpense, pk=pk)
        if item.is_active:
            item.pause()
            messages.success(request, f'"{item.name}" paused.')
        else:
            item.resume()
            messages.success(request, f'"{item.name}" resumed. Months missed while it was paused are skipped.')
        return redirect("recurring_list")


class RecurringDeleteView(FinanceManagerRequiredMixin, View):
    """POST-only. Expenses already created from it stay in the books."""

    http_method_names = ["post"]

    def post(self, request, pk):
        item = get_object_or_404(RecurringExpense, pk=pk)
        item.delete()
        messages.success(request, f'"{item.name}" deleted. Expenses already created from it are kept.')
        return redirect("recurring_list")


class RecurringGenerateView(FinanceManagerRequiredMixin, View):
    """POST-only. Create pending expenses for everything that has come due."""

    http_method_names = ["post"]

    def post(self, request):
        created = generate_due_expenses(user=request.user)
        if created:
            messages.success(request, f"Created {created} pending expense{'s' if created != 1 else ''}. They now wait for approval.")
        else:
            messages.info(request, "Nothing is due right now.")
        return redirect("recurring_list")