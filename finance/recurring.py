"""Turn recurring expenses into pending transactions."""
from django.db import transaction as db_transaction
from django.utils import timezone

from .models import RecurringExpense, Transaction


def pending_count(today=None):
    
    today = today or timezone.localdate()
    return sum(len(item.due_dates(today)) for item in RecurringExpense.objects.filter(is_active=True))


def generate_due_expenses(user=None, today=None):
   
    today = today or timezone.localdate()
    created = 0
    for pk in RecurringExpense.objects.filter(is_active=True).values_list("pk", flat=True):
        with db_transaction.atomic():
            item = RecurringExpense.objects.select_for_update().get(pk=pk)  # stops two runs overlapping
            for due in item.due_dates(today):
                Transaction.objects.create(
                    type=Transaction.Type.EXPENSE,
                    category=item.category,
                    department=item.department,
                    amount=item.amount,
                    date=due,
                    description=f"{item.name} (recurring)"[:255],
                    payment_method=item.payment_method,
                    supplier=item.supplier,
                    status=Transaction.Status.PENDING,
                    created_by=user,
                )
                item.last_generated = due
                created += 1
            item.save(update_fields=["last_generated"])
    return created