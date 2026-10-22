
from datetime import timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from .models import SupplierInvoice, Transaction

DUE_SOON_DAYS = 7


def payables_summary(today=None):
   
    today = today or timezone.localdate()
    open_invoices = list(SupplierInvoice.objects.outstanding().select_related("supplier"))
    soon_limit = today + timedelta(days=DUE_SOON_DAYS)
    overdue = [i for i in open_invoices if i.due_date < today]
    due_soon = [i for i in open_invoices if today <= i.due_date <= soon_limit]
    total = lambda items: sum((i.balance_due for i in items), Decimal("0.00"))
    return {
        "outstanding": open_invoices, "overdue": overdue, "due_soon": due_soon,
        "outstanding_total": total(open_invoices), "overdue_total": total(overdue), "due_soon_total": total(due_soon),
    }


def record_payment(invoice, user, amount, on, method, reference=""):
   
    with db_transaction.atomic():
        locked = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk)  # stops two payments racing
        if amount > locked.balance:
            raise ValueError("That is more than the balance still owed.")
        payment = Transaction(
            type=Transaction.Type.EXPENSE,
            category=locked.category,
            department=locked.department,
            amount=amount,
            date=on,
            description=f"Payment: {locked.supplier} invoice {locked.invoice_number}"[:255],
            payment_method=method,
            payment_reference=reference,
            supplier=locked.supplier,
            invoice=locked,
            created_by=user,
        )
        if payment.user_can_approve(user):
            payment.status = Transaction.Status.APPROVED
            payment.approved_by = user
        payment.save()
    return payment