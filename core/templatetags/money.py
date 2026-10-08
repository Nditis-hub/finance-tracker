from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

register = template.Library()


@register.filter
def money(value):
    """Show an amount with the currency label and thousands separators: KES 15,000.00"""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return value
    sign = "-" if amount < 0 else ""
    label = getattr(settings, "CURRENCY_LABEL", "")
    return f"{sign}{label} {abs(amount):,.2f}".replace("-  ", "-").strip()