import logging
from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from fleet.models.driver import DriverLicense
from fleet.forms.driver_license import DriverLicenseForm

logger = logging.getLogger("django")


class DriverLicenseListView(LoginRequiredMixin, View):
    template_name = "driver_license/list.html"

    def get(self, request):
        now = timezone.now()
        licenses = DriverLicense.objects.filter(
            tenant=request.user.profile.tenant
        ).select_related('tenant')
        
        context = {
            "licenses": licenses,
            "form": DriverLicenseForm(),
            "now": now
        }
        return render(request, self.template_name, context)

    def post(self, request):
        form = DriverLicenseForm(request.POST)
        if form.is_valid():
            license = form.save(commit=False)
            license.tenant = request.user.profile.tenant
            license.save()
            messages.success(request, "Driver License created successfully!")
            return redirect("fleet:driver-license-list")

        licenses = DriverLicense.objects.filter(
            tenant=request.user.profile.tenant
        ).select_related('tenant')
        context = {
            "licenses": licenses,
            "form": form,
            "now": timezone.now()
        }
        return render(request, self.template_name, context)


class DriverLicenseDetailView(LoginRequiredMixin, View):
    template_name = "driver_license/detail.html"

    def get(self, request, pk):
        license = get_object_or_404(
            DriverLicense.objects.select_related('tenant'),
            pk=pk,
            tenant=request.user.profile.tenant
        )
        context = {
            "license": license,
            "now": timezone.now()
        }
        return render(request, self.template_name, context)


class DriverLicenseUpdateView(LoginRequiredMixin, View):
    template_name = "driver_license/form.html"

    def get(self, request, pk):
        license = get_object_or_404(
            DriverLicense.objects.select_related('tenant'),
            pk=pk,
            tenant=request.user.profile.tenant
        )
        form = DriverLicenseForm(instance=license)
        context = {
            "form": form,
            "license": license,
            "action": "Update"
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        license = get_object_or_404(
            DriverLicense.objects.select_related('tenant'),
            pk=pk,
            tenant=request.user.profile.tenant
        )
        form = DriverLicenseForm(request.POST, instance=license)
        if form.is_valid():
            form.save()
            messages.success(request, "Driver License updated successfully!")
            return redirect("fleet:driver-license-detail", pk=license.pk)

        context = {
            "form": form,
            "license": license,
            "action": "Update"
        }
        return render(request, self.template_name, context)


class DriverLicenseDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        license = get_object_or_404(
            DriverLicense.objects.select_related('tenant'),
            pk=pk,
            tenant=request.user.profile.tenant
        )
        identifier = f"{license.name} ({license.license_number})"
        license.delete()
        messages.success(request, f"Driver License '{identifier}' deleted successfully!")
        return redirect("fleet:driver-license-list")


def get_driver_license_form(request, *args, **kwargs):
    """Helper function to get a form with tenant-filtered querysets"""
    form = DriverLicenseForm(*args, **kwargs)
    # Filter any querysets in the form by tenant
    for field in form.fields.values():
        if hasattr(field, "queryset"):
            field.queryset = field.queryset.filter(tenant=request.user.profile.tenant)
    return form
