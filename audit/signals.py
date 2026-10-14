from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.models import Category, Department
from finance.models import Booking, Budget, RecurringExpense, Supplier, Transaction

from .middleware import get_current_user
from .models import AuditLog

User = get_user_model()
TRACKED = (Transaction, Budget, Booking, Supplier, Category, Department, User, RecurringExpense)


def _record(instance, action):
    user = get_current_user()
    if user is not None and not user.is_authenticated:
        user = None
    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
    )


@receiver(post_save)
def log_save(sender, instance, created, update_fields=None, **kwargs):
    if sender not in TRACKED:
        return
    # Logging in only updates last_login; that is not worth an audit entry.
    if update_fields is not None and set(update_fields) == {"last_login"}:
        return
    _record(instance, AuditLog.Action.CREATED if created else AuditLog.Action.UPDATED)


@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    if sender in TRACKED:
        _record(instance, AuditLog.Action.DELETED)