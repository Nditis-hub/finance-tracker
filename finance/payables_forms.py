from decimal import Decimal

from django import forms
from django.utils import timezone

from core.models import Category

from .models import REFERENCE_METHODS, PaymentMethod, SupplierInvoice


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = SupplierInvoice
        fields = ["supplier", "invoice_number", "invoice_date", "due_date", "amount", "department", "category", "description"]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {"category": "Used when you record a payment, so it lands in the right expense category."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(kind=Category.Kind.EXPENSE)

    def clean_invoice_number(self):
        return self.cleaned_data["invoice_number"].strip()

    def clean(self):
        cleaned = super().clean()
        supplier, number = cleaned.get("supplier"), cleaned.get("invoice_number")
        if supplier and number:
            clash = SupplierInvoice.objects.filter(supplier=supplier, invoice_number__iexact=number).exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error("invoice_number", f"{supplier} already has an invoice numbered {number}.")
        amount = cleaned.get("amount")
        if amount is not None and self.instance.pk and amount < self.instance.amount_paid:
            self.add_error("amount", f"The amount cannot be less than what has already been paid ({self.instance.amount_paid}).")
        return cleaned


class PaymentForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    payment_method = forms.ChoiceField(choices=[("", "---------")] + PaymentMethod.choices)
    payment_reference = forms.CharField(
        max_length=60, required=False,
        help_text="Receipt, mobile money, cheque or transfer number. Required unless paid in cash.",
    )

    def __init__(self, *args, invoice, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice
        self.fields["amount"].initial = invoice.balance
        self.fields["amount"].help_text = f"Balance still owed: {invoice.balance}"
        self.fields["date"].initial = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        if amount is not None and amount > self.invoice.balance:
            self.add_error("amount", f"That is more than the balance still owed ({self.invoice.balance}).")
        method = cleaned.get("payment_method")
        reference = (cleaned.get("payment_reference") or "").strip()
        if method in REFERENCE_METHODS and not reference:
            self.add_error("payment_reference", "Enter a reference number for this payment method.")
        cleaned["payment_reference"] = reference
        return cleaned