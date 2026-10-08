from django.contrib import admin

from .models import Booking, Budget, Supplier, Transaction

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