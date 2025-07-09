# tenant/management/commands/cleanup_incomplete_onboarding.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.sessions.models import Session
from django.db import transaction
from fleet.models import Organization, Carrier
from tenant.models import Tenant, Profile

from django.contrib.auth.models import User


class Command(BaseCommand):
    help = "Cleans up incomplete onboarding data"

    def handle(self, *args, **options):
        cleaned_count = 0
        cutoff_time = timezone.now() - timedelta(hours=1)

        # First cleanup: Check sessions for incomplete onboarding
        old_sessions = Session.objects.filter(expire_date__lt=cutoff_time)
        for session in old_sessions:
            try:
                session_data = session.get_decoded()
                if (
                    "tenant_id" in session_data
                    and session_data.get("onboarding_status") != "completed"
                ):
                    tenant_id = session_data.get("tenant_id")
                    try:
                        with transaction.atomic():
                            tenant = Tenant.objects.get(id=tenant_id)
                            self.cleanup_tenant(tenant)
                            cleaned_count += 1
                    except Tenant.DoesNotExist:
                        continue
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Error processing session: {str(e)}")
                )
                continue

        # Second cleanup: Look for potentially orphaned tenants
        recent_tenants = Tenant.objects.filter(
            created_at__gte=timezone.now()
            - timedelta(hours=1)  # Tenants created in last hour
        )

        for tenant in recent_tenants:
            try:
                # Check if this tenant is incomplete (no users or incomplete setup)
                has_users = Profile.objects.filter(tenant=tenant).exists()
                has_organization = Organization.objects.filter(tenant=tenant).exists()
                has_carrier = Carrier.objects.filter(tenant=tenant).exists()

                # If tenant has no users and either missing organization or carrier, consider it incomplete
                if not has_users and (not has_organization or not has_carrier):
                    with transaction.atomic():
                        self.cleanup_tenant(tenant)
                        cleaned_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Cleaned up orphaned tenant: {tenant.name}"
                            )
                        )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Error processing tenant {tenant.id}: {str(e)}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully cleaned up {cleaned_count} incomplete onboarding records"
            )
        )

    def cleanup_tenant(self, tenant):
        """Helper method to cleanup a tenant and its related records"""
        # Delete in proper order to respect foreign key constraints
        Organization.objects.filter(tenant=tenant).delete()
        Carrier.objects.filter(tenant=tenant).delete()
        # Delete any associated profiles
        profiles = Profile.objects.filter(tenant=tenant)
        for profile in profiles:
            User.objects.filter(id=profile.user_id).delete()
        tenant.delete()
