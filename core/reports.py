"""Profit and loss by department. Only approved transactions count."""
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from finance.models import Transaction

from .models import Department

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ZERO = Decimal("0.00")
TENTH = Decimal("0.1")


def csv_safe(value):
    """Stop spreadsheet programs from running text that starts like a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _margin(profit, revenue):
    """Profit as a percentage of revenue, or None when there is no revenue to compare against."""
    if not revenue:
        return None
    return (profit / revenue * 100).quantize(TENTH)


def available_years():
    """Years that have approved transactions, newest first. The current year is always included."""
    years = {d.year for d in Transaction.objects.filter(status=Transaction.Status.APPROVED).dates("date", "year")}
    years.add(timezone.localdate().year)
    return sorted(years, reverse=True)


def department_pnl(year):
    """Revenue, expenses, profit and margin per department for a year, plus profit month by month."""
    rows = (
        Transaction.objects.filter(status=Transaction.Status.APPROVED, date__year=year)
        .annotate(month=TruncMonth("date"))
        .values("department_id", "month")
        .annotate(
            income=Sum("amount", filter=Q(type=Transaction.Type.INCOME)),
            expense=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
        )
        .order_by()
    )

    blank = lambda: {"revenue": ZERO, "expenses": ZERO, "months": [ZERO] * 12}
    by_department = {d.pk: {"name": d.name, **blank()} for d in Department.objects.order_by("name")}
    totals = blank()

    for row in rows:
        income, expense = row["income"] or ZERO, row["expense"] or ZERO
        index = row["month"].month - 1
        for bucket in (by_department[row["department_id"]], totals):
            bucket["revenue"] += income
            bucket["expenses"] += expense
            bucket["months"][index] += income - expense

    departments = list(by_department.values())
    for bucket in departments + [totals]:
        bucket["profit"] = bucket["revenue"] - bucket["expenses"]
        bucket["margin"] = _margin(bucket["profit"], bucket["revenue"])
    totals["name"] = "Total"

    return {"year": year, "month_labels": MONTH_LABELS, "departments": departments, "totals": totals}