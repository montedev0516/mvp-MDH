from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import transaction
from fleet.models import Carrier, Organization
from tenant.models import Role, Tenant


class OnboardingStatus:
    TENANT_CREATED = "tenant_created"
    ORGANIZATION_CREATED = "organization_created"
    CARRIER_CREATED = "carrier_created"
    COMPLETED = "completed"


class SuperUserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.profile.role != Role.SUPER_ADMIN:
            raise PermissionDenied("You do not have permission to perform this action.")
        return super().dispatch(request, *args, **kwargs)


class OnboardingCleanupMixin:
    def cleanup_incomplete_onboarding(self):
        tenant_id = self.request.session.get("tenant_id")
        if not tenant_id:
            return

        try:
            with transaction.atomic():
                tenant = Tenant.objects.get(id=tenant_id)
                status = self.request.session.get("onboarding_status")

                # If onboarding wasn't completed, clean up everything
                if status != OnboardingStatus.COMPLETED:
                    # Delete related records in reverse order
                    Carrier.objects.filter(tenant=tenant).delete()
                    Organization.objects.filter(tenant=tenant).delete()
                    tenant.delete()

                # Clear session data
                keys_to_clear = [
                    "tenant_id",
                    "organization_id",
                    "carrier_id",
                    "onboarding_status",
                ]
                for key in keys_to_clear:
                    self.request.session.pop(key, None)

        except Tenant.DoesNotExist:
            # Clear session if tenant doesn't exist
            for key in [
                "tenant_id",
                "organization_id",
                "carrier_id",
                "onboarding_status",
            ]:
                self.request.session.pop(key, None)


class OnboardingFlowMixin:
    def dispatch(self, request, *args, **kwargs):
        # Define the flow steps
        steps = {
            "onboarding": ["tenant_id"],
            "organization_setup": ["tenant_id"],
            "carrier_setup": ["tenant_id", "organization_id"],
            "user_setup": ["tenant_id", "organization_id", "carrier_id"],
        }

        current_url_name = request.resolver_match.url_name
        required_session_keys = steps.get(current_url_name, [])

        # Check if all required session keys exist
        missing_keys = [
            key for key in required_session_keys if not request.session.get(key)
        ]

        if missing_keys:
            messages.error(
                request,
                "Please complete the previous steps first. Missing data from: "
                + ", ".join(missing_keys),
            )
            # Redirect to appropriate step
            if "tenant_id" not in request.session:
                return redirect("tenant:onboarding")
            elif "organization_id" not in request.session:
                return redirect("tenant:organization_setup")
            elif "carrier_id" not in request.session:
                return redirect("tenant:carrier_setup")

        return super().dispatch(request, *args, **kwargs)
