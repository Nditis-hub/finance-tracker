from django.contrib import admin

from .models import Booking, Budget, RecurringExpense, Supplier, Transaction

admin.site.register(Supplier)
admin.site.register(Booking)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "type", "category", "department", "amount", "status")
    list_filter = ("type", "status", "department")


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("department", "amount", "period_start", "period_end", "is_current")
    list_filter = ("is_current", "department")

@admin.register(RecurringExpense)
class RecurringExpenseAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "amount", "day_of_month", "is_active", "last_generated")
    list_filter = ("is_active", "department")