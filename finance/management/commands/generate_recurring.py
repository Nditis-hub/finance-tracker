from django.core.management.base import BaseCommand

from finance.recurring import generate_due_expenses


class Command(BaseCommand):
    help = "Create pending expenses for every recurring expense that has come due. Safe to run daily."

    def handle(self, *args, **options):
        created = generate_due_expenses()
        self.stdout.write(self.style.SUCCESS(f"Created {created} pending expense{'s' if created != 1 else ''}."))