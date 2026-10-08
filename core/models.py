from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    """Income or expense category. The kind keeps income and expense categories separate."""

    class Kind(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices)

    class Meta:
        ordering = ["kind", "name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(fields=["name", "kind"], name="unique_category_name_per_kind"),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"