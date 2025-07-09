from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Exists, OuterRef, Q
from django.http import Http404
import logging

from fleet.models.driver import Driver, DriverEmployment, EmploymentStatus, DutyStatus
from fleet.forms.driver import DriverForm
from dispatch.models import DriverTruckAssignment, AssignmentStatus

logger = logging.getLogger(__name__)


class DriverView(LoginRequiredMixin, View):
    template_name = "driver/list.html"

    def get(self, request):
        now = timezone.now()
        drivers = Driver.objects.filter(
            tenant=request.user.profile.tenant
        ).annotate(
            has_active_assignment=Exists(
                DriverTruckAssignment.objects.filter(
                    driver=OuterRef('pk'),
                    start_date__lte=now,
                    end_date__gt=now
                )
            )
        ).select_related('drivers_license', 'carrier', 'tenant', 'driveremployment')
        
        context = {
            "drivers": drivers,
            "form": DriverForm(),
            "now": now
        }
        return render(request, self.template_name, context)

    def post(self, request):
        form = DriverForm(request.POST)
        if form.is_valid():
            driver = form.save(commit=False)
            driver.tenant = request.user.profile.tenant
            driver.save()
            
            # Create DriverEmployment record if it doesn't exist
            if not hasattr(driver, 'driveremployment'):
                DriverEmployment.objects.create(
                    driver=driver,
                    tenant=driver.tenant,
                    employment_status=EmploymentStatus.ACTIVE,
                    duty_status=DutyStatus.AVAILABLE,
                )
                logger.info(f"Created missing employment record for driver {driver.first_name} {driver.last_name}")
            else:
                logger.info(f"Driver {driver.first_name} {driver.last_name} already has employment record")
            
            messages.success(request, "Driver created successfully!")
            return redirect("fleet:driver-list")

        drivers = Driver.objects.filter(
            tenant=request.user.profile.tenant
        ).select_related('drivers_license', 'carrier', 'tenant', 'driveremployment')
        context = {"drivers": drivers, "form": form}
        return render(request, self.template_name, context)


class DriverDetailView(LoginRequiredMixin, View):
    template_name = "driver/detail.html"

    def get(self, request, pk):
        now = timezone.now()
        try:
            driver = Driver.objects.select_related(
                'drivers_license', 'carrier', 'tenant', 'driveremployment'
            ).annotate(
                has_active_assignment=Exists(
                    DriverTruckAssignment.objects.filter(
                        driver=OuterRef('pk'),
                        start_date__lte=now,
                        end_date__gt=now,
                        status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]
                    )
                )
            ).get(pk=pk, tenant=request.user.profile.tenant)
        except Driver.DoesNotExist:
            raise Http404("Driver not found")
        
        # Ensure DriverEmployment exists
        if not hasattr(driver, 'driveremployment') or driver.driveremployment is None:
            DriverEmployment.objects.create(
                driver=driver,
                tenant=driver.tenant,
                employment_status=EmploymentStatus.ACTIVE,
                duty_status=DutyStatus.AVAILABLE,
            )
            logger.info(f"Created missing employment record for driver {driver.first_name} {driver.last_name} during update")
        else:
            logger.info(f"Driver {driver.first_name} {driver.last_name} employment record verified during update")
        
        # Get active assignments
        active_assignments = DriverTruckAssignment.objects.filter(
            driver=driver,
            start_date__lte=now,
            end_date__gt=now,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]
        ).select_related('truck')
        
        context = {
            "driver": driver,
            "active_assignments": active_assignments,
            "now": now
        }
        return render(request, self.template_name, context)


class DriverCreateView(LoginRequiredMixin, View):
    template_name = "driver/form.html"

    def get(self, request):
        form = DriverForm()
        context = {"form": form, "action": "Create"}
        return render(request, self.template_name, context)

    def post(self, request):
        form = DriverForm(request.POST)
        if form.is_valid():
            driver = form.save(commit=False)
            driver.tenant = request.user.profile.tenant
            driver.save()
            
            # Create DriverEmployment record
            DriverEmployment.objects.create(
                driver=driver,
                tenant=driver.tenant,
                employment_status=EmploymentStatus.ACTIVE,
                duty_status=DutyStatus.AVAILABLE
            )
            
            messages.success(request, "Driver created successfully!")
            return redirect("fleet:driver-list")

        context = {"form": form, "action": "Create"}
        return render(request, self.template_name, context)


class DriverUpdateView(LoginRequiredMixin, View):
    template_name = "driver/update.html"

    def get(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk, tenant=request.user.profile.tenant)
        form = DriverForm(instance=driver)
        context = {"driver": driver, "form": form}
        return render(request, self.template_name, context)

    def post(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk, tenant=request.user.profile.tenant)
        form = DriverForm(request.POST, instance=driver)
        if form.is_valid():
            form.save()
            messages.success(request, "Driver updated successfully!")
            return redirect("fleet:driver-list")
        context = {"driver": driver, "form": form}
        return render(request, self.template_name, context)


class DriverDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            # First try to find the driver without tenant filter to debug
            driver_exists = Driver.objects.filter(id=pk).exists()
            if not driver_exists:
                logger.error(f"Driver with ID {pk} does not exist")
                messages.error(request, "Driver not found.")
                return redirect("fleet:driver-list")

            # Now check if driver exists for this tenant
            driver = Driver.objects.filter(
                id=pk, 
                tenant=request.user.profile.tenant
            ).first()
            
            if not driver:
                logger.error(
                    f"Driver with ID {pk} exists but belongs to a different tenant. "
                    f"Request tenant: {request.user.profile.tenant.id}"
                )
                messages.error(request, "Driver not found.")
                return redirect("fleet:driver-list")

            # Check for any active assignments
            has_active_assignments = DriverTruckAssignment.objects.filter(
                driver=driver,
                start_date__lte=timezone.now(),
                end_date__gt=timezone.now()
            ).exists()

            if has_active_assignments:
                messages.error(
                    request, 
                    "Cannot delete driver with active assignments. Please end all assignments first."
                )
                return redirect("fleet:driver-detail", pk=pk)

            # Check employment status before deletion
            if hasattr(driver, 'driveremployment') and driver.driveremployment:
                if driver.driveremployment.employment_status == 'terminated':
                    driver_name = f"{driver.first_name} {driver.last_name}"
                    driver.delete()
                    messages.success(request, f"Driver '{driver_name}' deleted successfully!")
                else:
                    messages.error(
                        request, 
                        "Cannot delete active driver. Please terminate employment first."
                    )
                    return redirect("fleet:driver-detail", pk=pk)
            else:
                # If no employment record, allow deletion
                driver_name = f"{driver.first_name} {driver.last_name}"
                driver.delete()
                messages.success(request, f"Driver '{driver_name}' deleted successfully!")
            
        except Exception as e:
            logger.exception(f"Error deleting driver {pk}: {str(e)}")
            messages.error(request, "An error occurred while deleting the driver.")
            
        return redirect("fleet:driver-list")
