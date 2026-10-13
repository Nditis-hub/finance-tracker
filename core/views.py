import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from accounts.permissions import FinanceManagerRequiredMixin
from finance.models import Booking, Budget, Transaction

from .analytics import get_chart_data
from .forecast import forecast_for
from .forms import CategoryForm, DepartmentForm
from .models import Category, Department
from .reports import available_years, csv_safe, department_pnl


def _sum(qs):
    return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")



@login_required
def dashboard(request):
    today = date.today()
    this_month = Transaction.objects.filter(
        status=Transaction.Status.APPROVED, date__year=today.year, date__month=today.month
    )
    income = _sum(this_month.filter(type=Transaction.Type.INCOME))
    expense = _sum(this_month.filter(type=Transaction.Type.EXPENSE))

    budgets = Budget.objects.filter(is_current=True).select_related("department")
    active_budgets = [b for b in budgets if not b.is_expired]
    budget_alerts = [b for b in active_budgets if b.alert_level in ("near", "over")]

    context = {
        "income": income,
        "expense": expense,
        "net": income - expense,
        "active_bookings": Booking.objects.filter(
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED]
        ).count(),
        "pending_approvals": Transaction.objects.filter(status=Transaction.Status.PENDING).count(),
        "budget_alerts": budget_alerts,
    }

    # Charts and forecasts show hotel-wide finances, so they are for admins and finance managers only.
    if request.user.can_manage_finance:
        data = get_chart_data()
        context["forecasts"] = [{"budget": b, "forecast": forecast_for(b)} for b in active_budgets]
        context["chart_data"] = {
            "months": data["months"][-6:],
            "income": data["income"][-6:],
            "expense": data["expense"][-6:],
            "budget_labels": [b.department.name for b in active_budgets],
            "budget_values": [round(float(b.percent_used), 1) for b in active_budgets],
        }
    return render(request, "core/dashboard.html", context)

# ---------- Categories (admins and finance managers only) ----------

class CategoryListView(FinanceManagerRequiredMixin, ListView):
    model = Category
    template_name = "core/category_list.html"
    context_object_name = "categories"


class CategoryCreateView(FinanceManagerRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "core/category_form.html"
    success_url = reverse_lazy("category_list")

    def form_valid(self, form):
        form.instance.name = form.instance.name.strip()
        messages.success(self.request, "Category added.")
        return super().form_valid(form)


class CategoryDeleteView(FinanceManagerRequiredMixin, View):
    """POST-only. A category already used by transactions cannot be deleted."""

    http_method_names = ["post"]

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        try:
            category.delete()
            messages.success(request, f'Category "{category.name}" deleted.')
        except ProtectedError:
            messages.error(request, f'"{category.name}" is used by existing transactions, so it cannot be deleted.')
        return redirect("category_list")


# ---------- Analytics (admins and finance managers only) ----------

class AnalyticsView(FinanceManagerRequiredMixin, TemplateView):
    template_name = "core/analytics.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["chart_data"] = get_chart_data()
        return ctx


# ---------- Departments (admins and finance managers only) ----------

class DepartmentListView(FinanceManagerRequiredMixin, ListView):
    model = Department
    template_name = "core/department_list.html"
    context_object_name = "departments"


class DepartmentCreateView(FinanceManagerRequiredMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = "core/department_form.html"
    success_url = reverse_lazy("department_list")

    def form_valid(self, form):
        messages.success(self.request, "Department added.")
        return super().form_valid(form)


class DepartmentUpdateView(FinanceManagerRequiredMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = "core/department_form.html"
    success_url = reverse_lazy("department_list")

    def form_valid(self, form):
        messages.success(self.request, "Department renamed.")
        return super().form_valid(form)


class DepartmentDeleteView(FinanceManagerRequiredMixin, View):
    """POST-only. A department with transactions, bookings or budgets cannot be deleted."""

    http_method_names = ["post"]

    def post(self, request, pk):
        department = get_object_or_404(Department, pk=pk)
        try:
            department.delete()
            messages.success(request, f'Department "{department.name}" deleted.')
        except ProtectedError:
            messages.error(
                request,
                f'"{department.name}" has transactions, bookings or budgets, so it cannot be deleted. You can rename it instead.',
            )
        return redirect("department_list")

        

# ---------- Profit and loss by department (admins and finance managers only) ----------

def _selected_year(request):
    """The year from ?year=, falling back to the current year when it is missing or not sensible."""
    try:
        year = int(request.GET.get("year", ""))
    except ValueError:
        return date.today().year
    return year if 2000 <= year <= 2100 else date.today().year


class ProfitLossView(FinanceManagerRequiredMixin, TemplateView):
    template_name = "core/profit_loss.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        year = _selected_year(self.request)
        report = department_pnl(year)
        ctx["report"] = report
        ctx["years"] = available_years()
        ctx["year"] = year
        ctx["chart_data"] = {
            "labels": [d["name"] for d in report["departments"]],
            "revenue": [float(d["revenue"]) for d in report["departments"]],
            "expenses": [float(d["expenses"]) for d in report["departments"]],
        }
        return ctx


class ProfitLossExportView(FinanceManagerRequiredMixin, View):
    """Download the profit and loss report for a year as a spreadsheet file."""

    http_method_names = ["get"]

    def get(self, request):
        year = _selected_year(request)
        report = department_pnl(year)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="profit-and-loss-{year}.csv"'
        response.write("\ufeff")  # lets Excel read the file as UTF-8
        writer = csv.writer(response)
        writer.writerow(["Department", "Revenue", "Expenses", "Profit", "Margin %"]
                        + [f"{m} profit" for m in report["month_labels"]])
        for d in report["departments"] + [report["totals"]]:
            writer.writerow([
                csv_safe(d["name"]), d["revenue"], d["expenses"], d["profit"],
                "" if d["margin"] is None else d["margin"], *d["months"],
            ])
        return response