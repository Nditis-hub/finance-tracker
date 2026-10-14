import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction as db_transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.models import Category, Department


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    CHEQUE = "cheque", "Cheque"
    OTHER = "other", "Other"


# Payment methods that should carry a reference number (receipt, transaction code, cheque number...).
REFERENCE_METHODS = {
    PaymentMethod.CARD,
    PaymentMethod.BANK_TRANSFER,
    PaymentMethod.MOBILE_MONEY,
    PaymentMethod.CHEQUE,
}

MONEY = dict(max_digits=12, decimal_places=2)
POSITIVE = [MinValueValidator(Decimal("0.01"))]


class Supplier(models.Model):
    class Kind(models.TextChoices):
        FOOD = "food", "Food & Beverage"
        LINENS = "linens", "Linens & Housekeeping"
        MAINTENANCE = "maintenance", "Maintenance & Repairs"
        UTILITIES = "utilities", "Utilities"
        FURNITURE = "furniture", "Furniture & Fixtures"
        EVENTS = "events", "Event Equipment"
        OTHER = "other", "Other"

    name = models.CharField(max_length=150)
    contact = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Booking(models.Model):
    class Type(models.TextChoices):
        ACCOMMODATION = "accommodation", "Accommodation"
        RESTAURANT = "restaurant", "Restaurant"
        EVENT = "event", "Event"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    guest_name = models.CharField(max_length=150)
    booking_type = models.CharField(max_length=20, choices=Type.choices)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="bookings")
    amount = models.DecimalField(validators=POSITIVE, **MONEY)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    check_in = models.DateField()
    check_out = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    payment_reference = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.check_out and self.check_in and self.check_out < self.check_in:
            raise ValidationError({"check_out": "Check-out cannot be before check-in."})

    @property
    def is_editable(self):
        """Paid bookings are locked, because their income is already in the ledger."""
        return self.status != self.Status.PAID

    INCOME_CATEGORY_NAMES = {
        "accommodation": "Room Revenue",
        "restaurant": "Restaurant Sales",
        "event": "Event Bookings",
    }

    def record_payment(self, user):
        """Create the income transaction for a paid booking. Safe to call twice: it only records once."""
        if self.transactions.filter(type=Transaction.Type.INCOME).exists():
            return None
        category, _ = Category.objects.get_or_create(
            name=self.INCOME_CATEGORY_NAMES[self.booking_type], kind=Category.Kind.INCOME
        )
        return Transaction.objects.create(
            type=Transaction.Type.INCOME,
            category=category,
            department=self.department,
            amount=self.amount,
            date=timezone.localdate(),
            description=f"Booking payment: {self.guest_name}",
            payment_method=self.payment_method,
            payment_reference=self.payment_reference,
            booking=self,
            status=Transaction.Status.APPROVED,
            created_by=user,
            approved_by=user,
        )

    def __str__(self):
        return f"{self.guest_name} ({self.get_booking_type_display()})"


class Transaction(models.Model):
    class Type(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        VOIDED = "voided", "Voided"

    type = models.CharField(max_length=10, choices=Type.choices)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="transactions")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="transactions")
    amount = models.DecimalField(validators=POSITIVE, **MONEY)
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    payment_reference = models.CharField(max_length=60, blank=True)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="transactions_created")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions_approved")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def clean(self):
        if self.category_id and self.category.kind != self.type:
            raise ValidationError({"category": f"Pick an {self.type} category for an {self.type} transaction."})

    @property
    def requires_admin_approval(self):
        """Expenses above EXPENSE_APPROVAL_LIMIT need an admin, not just a finance manager."""
        limit = getattr(settings, "EXPENSE_APPROVAL_LIMIT", None)
        return bool(limit) and self.type == self.Type.EXPENSE and self.amount > limit

    def user_can_approve(self, user):
        """Admins can approve anything. Finance managers can approve everything except
        expenses above the approval limit."""
        if not user.can_manage_finance:
            return False
        return user.is_hotel_admin or not self.requires_admin_approval

    def approve(self, user):
        if not self.user_can_approve(user):
            if user.can_manage_finance:
                raise PermissionError("Expenses above the approval limit can only be approved by an admin.")
            raise PermissionError("Only admins and finance managers can approve transactions.")
        self.status = self.Status.APPROVED
        self.approved_by = user
        self.rejection_reason = ""
        self.save(update_fields=["status", "approved_by", "rejection_reason"])

    def reject(self, user, reason=""):
        if not user.can_manage_finance:
            raise PermissionError("Only admins and finance managers can reject transactions.")
        self.status = self.Status.REJECTED
        self.approved_by = user
        self.rejection_reason = reason.strip()[:255]
        self.save(update_fields=["status", "approved_by", "rejection_reason"])

    def void(self, user):
        """Cancel an approved transaction. It stays on record but no longer counts anywhere."""
        if not user.can_manage_finance:
            raise PermissionError("Only admins and finance managers can void transactions.")
        if self.status != self.Status.APPROVED:
            raise ValueError("Only approved transactions can be voided.")
        self.status = self.Status.VOIDED
        self.save(update_fields=["status"])

    def user_can_modify(self, user):
        """Pending and rejected entries can be edited or deleted by whoever recorded them,
        or by an admin or finance manager. Approved entries are locked; they can only be voided."""
        if self.status not in (self.Status.PENDING, self.Status.REJECTED):
            return False
        return user.can_manage_finance or self.created_by_id == user.pk

    def __str__(self):
        return f"{self.get_type_display()} {self.amount} on {self.date}"


class Budget(models.Model):
    """A budget version for a department. Only one version per department is current;
    older versions stay as history."""

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="budgets")
    amount = models.DecimalField(validators=POSITIVE, **MONEY)
    period_start = models.DateField()
    period_end = models.DateField()
    is_current = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["department__name", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["department"], condition=Q(is_current=True), name="one_current_budget_per_department"
            ),
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F("period_start")), name="budget_period_end_after_start"
            ),
        ]

    def clean(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValidationError({"period_end": "Period end cannot be before period start."})

    def save(self, *args, **kwargs):
        # A new current version retires the previous one, atomically.
        if self.is_current:
            with db_transaction.atomic():
                Budget.objects.filter(department=self.department, is_current=True).exclude(pk=self.pk).update(is_current=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    @property
    def spent(self):
        """Approved expenses for this department inside the budget period."""
        total = Transaction.objects.filter(
            department=self.department,
            type=Transaction.Type.EXPENSE,
            status=Transaction.Status.APPROVED,
            date__range=(self.period_start, self.period_end),
        ).aggregate(total=Sum("amount"))["total"]
        return total or Decimal("0.00")

    @property
    def remaining(self):
        return self.amount - self.spent

    @property
    def percent_used(self):
        return (self.spent / self.amount * 100) if self.amount else Decimal("0")

    @property
    def percent_used_capped(self):
        """Progress-bar width: 0 to 100 as a whole number."""
        return int(min(self.percent_used, Decimal("100")))

    @property
    def alert_level(self):
        pct = self.percent_used
        if pct >= 100:
            return "over"
        if pct >= 80:
            return "near"
        return "ok"

    @property
    def is_expired(self):
        """True once the budget period has ended."""
        return self.period_end < timezone.localdate()

    def __str__(self):
        return f"{self.department} budget {self.period_start} to {self.period_end}"

        

class RecurringExpense(models.Model):
    """An expense that repeats every month, such as rent, salaries or utilities."""

    name = models.CharField(max_length=120)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="recurring_expenses")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="recurring_expenses")
    amount = models.DecimalField(validators=POSITIVE, **MONEY)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="recurring_expenses")
    day_of_month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="If a month is shorter (for example day 31 in February), the last day of that month is used.",
    )
    start_date = models.DateField(help_text="The first expense is created on the first due date on or after this date.")
    end_date = models.DateField(null=True, blank=True, help_text="Optional. No expenses are created after this date.")
    is_active = models.BooleanField(default=True)
    last_generated = models.DateField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def clean(self):
        errors = {}
        if self.category_id and self.category.kind != Category.Kind.EXPENSE:
            errors["category"] = "Pick an expense category."
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be before the start date."
        if errors:
            raise ValidationError(errors)

    # ----- schedule -----

    def _due_in_month(self, year, month):
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(self.day_of_month, last_day))

    def _first_open_day(self):
        """The earliest day an expense could still be created for."""
        return self.start_date if self.last_generated is None else self.last_generated + timedelta(days=1)

    def due_dates(self, today=None):
        """Dates up to today that have not been turned into an expense yet."""
        today = today or timezone.localdate()
        lower = self._first_open_day()
        upper = min(today, self.end_date) if self.end_date else today
        dates = []
        year, month = lower.year, lower.month
        while date(year, month, 1) <= upper:
            due = self._due_in_month(year, month)
            if lower <= due <= upper:
                dates.append(due)
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return dates

    def next_due(self):
        """The next date an expense is due (it may already be in the past), or None if the schedule is finished."""
        lower = self._first_open_day()
        year, month = lower.year, lower.month
        for _ in range(14):
            due = self._due_in_month(year, month)
            if due >= lower:
                return None if self.end_date and due > self.end_date else due
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return None

    def pause(self):
        self.is_active = False
        self.save(update_fields=["is_active"])

    def resume(self, today=None):
        """Switch back on. Months missed while paused are skipped, not created afterwards."""
        today = today or timezone.localdate()
        missed = self.due_dates(today - timedelta(days=1))
        if missed:
            self.last_generated = max(missed)
        self.is_active = True
        self.save(update_fields=["is_active", "last_generated"])

    def __str__(self):
        return self.name