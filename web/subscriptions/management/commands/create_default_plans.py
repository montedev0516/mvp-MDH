from django.core.management.base import BaseCommand
from subscriptions.models import SubscriptionPlan
import uuid

DEFAULT_PLANS = [
    {
        "name": "Basic",
        "description": "Basic plan for small operations",
        "max_active_drivers": 10,
        "max_active_trucks": 10,
        "max_organizations": 1,
        "monthly_order_limit": 50,
        "monthly_license_limit": 10,
        "monthly_token_limit": 10000,
        "storage_limit_mb": 1024,  # 1GB
        "price_monthly": 49.99,
        "price_yearly": 499.99,
        "is_custom": False,
    },
    {
        "name": "Professional",
        "description": "Professional plan for growing businesses",
        "max_active_drivers": 50,
        "max_active_trucks": 50,
        "max_organizations": 3,
        "monthly_order_limit": 200,
        "monthly_license_limit": 40,
        "monthly_token_limit": 50000,
        "storage_limit_mb": 5120,  # 5GB
        "price_monthly": 149.99,
        "price_yearly": 1499.99,
        "is_custom": False,
    },
    {
        "name": "Enterprise",
        "description": "Enterprise plan for large organizations",
        "max_active_drivers": 1000,
        "max_active_trucks": 1000,
        "max_organizations": 10,
        "monthly_order_limit": 1000,
        "monthly_license_limit": 200,
        "monthly_token_limit": 200000,
        "storage_limit_mb": 20480,  # 20GB
        "price_monthly": 499.99,
        "price_yearly": 4999.99,
        "is_custom": False,
    },
]


class Command(BaseCommand):
    help = "Verifies and creates default subscription plans if they do not exist"

    def handle(self, *args, **kwargs):
        self.stdout.write("Verifying subscription plans...")

        created_count = 0
        updated_count = 0

        for plan_data in DEFAULT_PLANS:
            plan, created = SubscriptionPlan.objects.get_or_create(
                name=plan_data["name"],
                defaults={"id": uuid.uuid4(), "is_active": True, **plan_data},
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created {plan.name} plan"))
            else:
                # Update existing plan
                for key, value in plan_data.items():
                    setattr(plan, key, value)
                plan.save()
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"Updated {plan.name} plan"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished! Created {created_count} plans, updated {updated_count} plans."
            )
        )

        # Print all plans for verification
        self.stdout.write("\nCurrent plans:")
        for plan in SubscriptionPlan.objects.all():
            self.stdout.write(f"- {plan.name} (ID: {plan.id})")
