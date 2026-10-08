from django.contrib import admin

from .models import Category, Department

admin.site.register(Department)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind")
    list_filter = ("kind",)