from django import forms

from core.models import Category, Department

from .models import REFERENCE_METHODS, Booking, Budget, PaymentMethod, Supplier, Transaction


REFERENCE_HELP = "Receipt, mobile money, cheque or transfer number. Required unless paid in cash."


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["type", "category", "department", "amount", "date", "description",
                  "payment_method", "payment_reference", "supplier"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        help_texts = {"payment_reference": REFERENCE_HELP}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].required = False
        self.fields["supplier"].empty_label = "None"
        self.fields["payment_method"].required = True

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("payment_method")
        reference = (cleaned.get("payment_reference") or "").strip()
        if method in REFERENCE_METHODS and not reference:
            self.add_error("payment_reference", "Enter a reference number for this payment method.")
        cleaned["payment_reference"] = reference
        return cleaned


class TransactionFilterForm(forms.Form):
    status = forms.ChoiceField(required=False, choices=[("", "All statuses")] + Transaction.Status.choices)
    type = forms.ChoiceField(required=False, choices=[("", "Income and expenses")] + Transaction.Type.choices)
    department = forms.ModelChoiceField(required=False, queryset=Department.objects.all(), empty_label="All departments")
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = "form-select" if isinstance(field, (forms.ChoiceField, forms.ModelChoiceField)) else "form-control"
            field.widget.attrs["class"] = css


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["department", "amount", "period_start", "period_end"]
        widgets = {
            "period_start": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "period_end": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ["guest_name", "booking_type", "department", "amount", "status", "check_in", "check_out",
                  "payment_method", "payment_reference"]
        widgets = {
            "check_in": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "check_out": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {"payment_method": "Optional. If the booking is paid, this is copied to the income record."}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Only admins and finance managers can record a booking as paid.
        if user is not None and not user.can_manage_finance:
            self.fields["status"].choices = [c for c in Booking.Status.choices if c[0] != Booking.Status.PAID]


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "contact", "category", "description"]


class BookingEditForm(forms.ModelForm):
    """Edit a booking's details. Its status is changed from the Bookings list."""

    class Meta:
        model = Booking
        fields = ["guest_name", "booking_type", "department", "amount", "check_in", "check_out",
                  "payment_method", "payment_reference"]
        widgets = {
            "check_in": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "check_out": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {"payment_method": "Optional. If the booking is paid, this is copied to the income record."}