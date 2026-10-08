"""Spending forecast for a department budget.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Optional

from django.db.models import Sum
from django.utils import timezone

from finance.models import Transaction

CENTS = Decimal("0.01")
EARLY_DAYS = 7  # estimates from fewer days of data can swing a lot


@dataclass
class Forecast:
    status: str  # not_started, ended, no_spending, over, run_out or on_track
    spent_to_date: Decimal = Decimal("0.00")
    daily_rate: Decimal = Decimal("0.00")
    projected_total: Decimal = Decimal("0.00")
    projected_remaining: Decimal = Decimal("0.00")  # budget minus projected total (negative = overspend)
    over_by: Decimal = Decimal("0.00")
    exhaust_date: Optional[date] = None
    elapsed_days: int = 0
    total_days: int = 0
    low_confidence: bool = False

    @property
    def at_risk(self):
        return self.status in ("run_out", "over")


def _spent_to_date(budget, today):
    total = Transaction.objects.filter(
        department=budget.department,
        type=Transaction.Type.EXPENSE,
        status=Transaction.Status.APPROVED,
        date__range=(budget.period_start, today),
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0.00")


def forecast_for(budget, today=None):
    """Forecast how a budget will end up, using only spending up to `today`."""
    today = today or timezone.localdate()
    total_days = (budget.period_end - budget.period_start).days + 1

    if today < budget.period_start:
        return Forecast("not_started", total_days=total_days)
    if today > budget.period_end:
        return Forecast("ended", total_days=total_days, elapsed_days=total_days)

    elapsed = (today - budget.period_start).days + 1
    spent = _spent_to_date(budget, today)
    common = dict(spent_to_date=spent, elapsed_days=elapsed, total_days=total_days,
                  low_confidence=elapsed < EARLY_DAYS)

    if spent >= budget.amount:
        return Forecast("over", over_by=spent - budget.amount, **common)
    if spent == 0:
        return Forecast("no_spending", projected_remaining=budget.amount, **common)

    rate = (spent / elapsed).quantize(CENTS)
    projected = (spent / elapsed * total_days).quantize(CENTS)
    remaining = budget.amount - projected
    if projected > budget.amount:
        days_left = ((budget.amount - spent) / (spent / elapsed)).to_integral_value(rounding=ROUND_CEILING)
        return Forecast("run_out", daily_rate=rate, projected_total=projected, projected_remaining=remaining,
                        exhaust_date=today + timedelta(days=int(days_left)), **common)
    return Forecast("on_track", daily_rate=rate, projected_total=projected, projected_remaining=remaining, **common)