from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth

from finance.models import Booking, Transaction


def _num(value):
    return float(value or 0)


def get_chart_data():
    """Numbers for the analytics charts. Only approved transactions are counted."""
    approved = Transaction.objects.filter(status=Transaction.Status.APPROVED)

    monthly = (
        approved.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(
            income=Sum("amount", filter=Q(type=Transaction.Type.INCOME)),
            expense=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
        )
        .order_by("month")
    )
    revenue = (
        approved.filter(type=Transaction.Type.INCOME)
        .values("department__name").annotate(total=Sum("amount")).order_by("-total")
    )
    expenses = (
        approved.filter(type=Transaction.Type.EXPENSE)
        .values("category__name").annotate(total=Sum("amount")).order_by("-total")
    )
    suppliers = (
        approved.filter(type=Transaction.Type.EXPENSE, supplier__isnull=False)
        .values("supplier__name").annotate(total=Sum("amount")).order_by("-total")[:5]
    )
    bookings = (
        Booking.objects.values("status")
        .annotate(total=Sum("amount"), count=Count("id")).order_by("status")
    )
    status_labels = dict(Booking.Status.choices)

    return {
        "months": [m["month"].strftime("%Y-%m") for m in monthly],
        "income": [_num(m["income"]) for m in monthly],
        "expense": [_num(m["expense"]) for m in monthly],
        "dept_labels": [r["department__name"] for r in revenue],
        "dept_values": [_num(r["total"]) for r in revenue],
        "category_labels": [r["category__name"] for r in expenses],
        "category_values": [_num(r["total"]) for r in expenses],
        "supplier_labels": [r["supplier__name"] for r in suppliers],
        "supplier_values": [_num(r["total"]) for r in suppliers],
        "booking_labels": [f'{status_labels[r["status"]]} ({r["count"]})' for r in bookings],
        "booking_values": [_num(r["total"]) for r in bookings],
    }