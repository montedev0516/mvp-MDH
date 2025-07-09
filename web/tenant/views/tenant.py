# Create your views here.
import logging
from django.views.generic import View
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.views.generic import UpdateView
from django.urls import reverse_lazy
from tenant.forms import (
    UserProfileForm,
    CarrierUpdateForm,
    OrganizationForm,
)
from fleet.models import Carrier, Organization
from tenant.models import Role

logger = logging.getLogger("django")


class TenantHome(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "index.html", {})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("tenant:home")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "Login successful!")

            # Get the next URL from the query parameters, default to tenant:home
            next_url = request.GET.get("next", "tenant:home")
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, "registration/login.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("tenant:login")


class ProfileView(LoginRequiredMixin, UpdateView):
    form_class = UserProfileForm
    template_name = "profile/detail.html"
    success_url = reverse_lazy("tenant:profile")

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["profile"] = self.request.user.profile
        
        # Get the carrier for this tenant
        carrier = Carrier.objects.filter(
            tenant=self.request.user.profile.tenant.id
        ).first()
        context["carrier"] = carrier

        # Get or create organization for this tenant
        organization, created = Organization.objects.get_or_create(
            tenant=self.request.user.profile.tenant,
            defaults={
                'name': self.request.user.profile.tenant.name,
                'address': '',
                'commission_percentage': 12.0,
                'commission_currency': 'CAD'
            }
        )
        
        # Link the organization to the carrier if both exist
        if carrier and organization and not organization.carrier:
            organization.carrier = carrier
            organization.save()
        
        context["organization"] = organization

        if self.request.user.profile.role == Role.ADMIN:
            context["carrier_form"] = CarrierUpdateForm(
                instance=carrier
            )
            context["org_form"] = OrganizationForm(
                instance=organization
            )

        return context

    def post(self, request, *args, **kwargs):
        form_type = request.POST.get("form_type")

        if request.user.profile.role != Role.ADMIN:
            return super().post(request, *args, **kwargs)

        if form_type == "profile":
            return super().post(request, *args, **kwargs)

        elif form_type == "carrier":
            carrier_form = CarrierUpdateForm(
                request.POST,
                instance=Carrier.objects.filter(
                    tenant=request.user.profile.tenant.id
                ).first(),
            )
            if carrier_form.is_valid():
                carrier_form.save()
                messages.success(request, "Carrier details updated successfully!")

        elif form_type == "organization":
            organization = Organization.objects.filter(
                tenant=request.user.profile.tenant
            ).first()
            org_form = OrganizationForm(
                request.POST,
                instance=organization
            )
            if org_form.is_valid():
                org_form.save()
                messages.success(request, "Organization details updated successfully!")

        return redirect("tenant:profile")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Profile updated successfully!")
        return response
