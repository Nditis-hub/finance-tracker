from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class HotelUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Hotel role", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {"fields": ("email", "role")}),
    )
    list_display = ("username", "email", "role", "is_active")
    list_filter = ("role", "is_active")