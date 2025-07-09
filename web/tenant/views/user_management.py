import logging
from django.views.generic import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.db import transaction
from django_tables2 import SingleTableView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponseRedirect
from tenant.forms import (
    TenantForm,
    CarrierForm,
    OrganizationForm,
    CustomUserCreationForm,
    UserEditForm,
    UserAddForm,
)
from tenant.models import Tenant, User, Role
from fleet.models import Carrier, Organization
from tenant.tables import UserTable
from django.shortcuts import redirect
from django.db.models import Q
from django.contrib.auth.hashers import make_password
from .mixins import (
    SuperUserRequiredMixin,
    OnboardingFlowMixin,
    OnboardingCleanupMixin,
    OnboardingStatus,
)

logger = logging.getLogger("django")


class OnboardingWizardView(SuperUserRequiredMixin, OnboardingCleanupMixin, CreateView):
    template_name = "user_management/onboarding_wizard.html"
    form_class = TenantForm
    success_url = reverse_lazy("tenant:organization_setup")

    def dispatch(self, request, *args, **kwargs):
        # Clean up any existing incomplete onboarding
        self.cleanup_incomplete_onboarding()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            tenant = form.save()
            self.request.session["tenant_id"] = str(tenant.id)
            self.request.session["onboarding_status"] = OnboardingStatus.TENANT_CREATED
            messages.success(self.request, "Tenant created successfully!")
            return super().form_valid(form)


class OrganizationSetupView(
    SuperUserRequiredMixin, OnboardingFlowMixin, OnboardingCleanupMixin, CreateView
):
    template_name = "user_management/organization_setup.html"
    form_class = OrganizationForm
    success_url = reverse_lazy("tenant:carrier_setup")

    def form_valid(self, form):
        try:
            with transaction.atomic():
                tenant_id = self.request.session.get("tenant_id")
                tenant = Tenant.objects.get(id=tenant_id)

                organization = form.save(commit=False)
                organization.tenant = tenant
                organization.save()

                self.request.session["organization_id"] = str(organization.id)
                self.request.session["onboarding_status"] = OnboardingStatus.ORGANIZATION_CREATED
                messages.success(self.request, "Organization created successfully!")
                return super().form_valid(form)
        except Tenant.DoesNotExist:
            messages.error(
                self.request, "Tenant not found. Please start from the beginning."
            )
            return redirect("tenant:onboarding")


class CarrierSetupView(
    SuperUserRequiredMixin, OnboardingFlowMixin, OnboardingCleanupMixin, CreateView
):
    template_name = "user_management/carrier_setup.html"
    form_class = CarrierForm
    success_url = reverse_lazy("tenant:user_setup")

    def form_valid(self, form):
        try:
            with transaction.atomic():
                tenant_id = self.request.session.get("tenant_id")
                organization_id = self.request.session.get("organization_id")
                tenant = Tenant.objects.get(id=tenant_id)
                organization = Organization.objects.get(id=organization_id)

                carrier = form.save(commit=False)
                carrier.tenant = tenant
                carrier.save()

                # Link the organization to the carrier
                organization.carrier = carrier
                organization.save()

                self.request.session["carrier_id"] = str(carrier.id)
                self.request.session["onboarding_status"] = OnboardingStatus.CARRIER_CREATED
                messages.success(self.request, "Carrier created successfully!")
                return super().form_valid(form)
        except (Tenant.DoesNotExist, Organization.DoesNotExist):
            messages.error(
                self.request, "Required data not found. Please start from the beginning."
            )
            return redirect("tenant:onboarding")


class UserSetupView(
    SuperUserRequiredMixin, OnboardingFlowMixin, OnboardingCleanupMixin, CreateView
):
    template_name = "user_management/user_setup.html"
    form_class = CustomUserCreationForm
    success_url = reverse_lazy("tenant:user_list")

    def form_valid(self, form):
        try:
            with transaction.atomic():
                tenant_id = self.request.session.get("tenant_id")
                tenant = Tenant.objects.get(id=tenant_id)

                user = form.save()
                user._tenant = tenant  # Keep for backward compatibility if needed

                profile = user.profile
                profile.tenant = tenant  # Add this line to properly set the tenant
                profile.role = form.cleaned_data["role"]
                profile.save()

                self.request.session["onboarding_status"] = OnboardingStatus.COMPLETED

                # Clear session data after successful completion
                for key in [
                    "tenant_id",
                    "organization_id",
                    "carrier_id",
                    "onboarding_status",
                ]:
                    self.request.session.pop(key, None)

                messages.success(self.request, "Setup completed successfully!")
                return super().form_valid(form)
        except Tenant.DoesNotExist:
            messages.error(
                self.request,
                "Required data not found. Please start from the beginning.",
            )
            return redirect("tenant:onboarding")


class UserListView(SuperUserRequiredMixin, SingleTableView):
    model = User
    table_class = UserTable
    template_name = "user_management/user_list.html"
    table_pagination = {"per_page": 10}

    def get_queryset(self):
        queryset = (
            User.objects.all()
            .select_related("profile__tenant")
            .order_by("-date_joined")
        )

        # Filter by tenant if selected
        selected_tenant = self.request.GET.get("tenant")
        if selected_tenant:
            queryset = queryset.filter(profile__tenant_id=selected_tenant)

        # Search functionality
        search_query = self.request.GET.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query)
                | Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tenants"] = Tenant.objects.all().order_by("name")
        context["selected_tenant"] = self.request.GET.get("tenant")
        context["search_query"] = self.request.GET.get("search", "")
        return context


class UserEditView(SuperUserRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserEditForm
    template_name = "user_management/user_edit.html"
    success_url = reverse_lazy("tenant:user_list")
    success_message = "User updated successfully!"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Only show password fields for superadmin
        if self.request.user.profile.role != Role.SUPER_ADMIN:
            if "new_password" in form.fields:
                del form.fields["new_password"]
            if "confirm_password" in form.fields:
                del form.fields["confirm_password"]
        return form

    def form_valid(self, form):
        user = form.save(commit=False)

        # Handle password update if provided
        new_password = form.cleaned_data.get("new_password")
        if new_password and self.request.user.profile.role == Role.SUPER_ADMIN:
            user.password = make_password(new_password)
            messages.success(self.request, "Password updated successfully!")

        user.save()

        # Update the profile role
        user.profile.role = form.cleaned_data["role"]
        user.profile.save()

        return super().form_valid(form)


class UserDeleteView(SuperUserRequiredMixin, DeleteView):
    model = User
    success_url = reverse_lazy("tenant:user_list")

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        self.object.is_active = False  # Soft delete
        self.object.save()
        messages.success(request, "User deactivated successfully!")

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"status": "success"})
        return HttpResponseRedirect(success_url)


class UserAddView(SuperUserRequiredMixin, SuccessMessageMixin, CreateView):
    template_name = "user_management/user_add.html"
    form_class = UserAddForm
    success_url = reverse_lazy("tenant:user_list")
    success_message = "User was created successfully!"

    def form_valid(self, form):
        try:
            with transaction.atomic():
                user = form.save()
                tenant = form.cleaned_data["tenant"]
                user._tenant = tenant

                profile = user.profile
                profile.tenant = tenant
                profile.role = form.cleaned_data["role"]
                profile.save()

                return super().form_valid(form)
        except Exception as e:
            messages.error(self.request, f"Error creating user: {str(e)}")
            return self.form_invalid(form)
