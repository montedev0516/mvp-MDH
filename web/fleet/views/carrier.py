from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Exists, OuterRef, Q
from fleet.models.carrier import Carrier
from fleet.forms.carrier import CarrierForm
from dispatch.models import Dispatch, DriverTruckAssignment
from django.db.models import Prefetch
from fleet.models.driver import Driver


def get_carrier_form(request, *args, **kwargs):
    """Helper function to get a form with tenant-filtered querysets"""
    form = CarrierForm(*args, **kwargs)
    # Filter any querysets in the form by tenant
    for field in form.fields.values():
        if hasattr(field, "queryset"):
            if hasattr(field.queryset.model, "tenant"):
                field.queryset = field.queryset.filter(
                    tenant=request.user.profile.tenant
                )
    return form


class CarrierListView(LoginRequiredMixin, View):
    template_name = "carrier/list.html"

    def get(self, request):
        now = timezone.now()
        carriers = Carrier.objects.filter(
            tenant=request.user.profile.tenant,
            deleted_at__isnull=True  # Only get non-deleted carriers
        ).annotate(
            has_active_assignment=Exists(
                DriverTruckAssignment.objects.filter(
                    dispatch__carrier=OuterRef('pk'),
                    start_date__lte=now,
                    end_date__gt=now
                )
            )
        ).select_related('tenant')
        
        context = {
            "carriers": carriers,
            "form": CarrierForm(),
            "now": now
        }
        return render(request, self.template_name, context)

    def post(self, request):
        form = CarrierForm(request.POST)
        if form.is_valid():
            carrier = form.save(commit=False)
            carrier.tenant = request.user.profile.tenant
            carrier.save()
            messages.success(request, "Carrier created successfully!")
            return redirect("fleet:carrier-list")

        carriers = Carrier.objects.filter(
            tenant=request.user.profile.tenant,
            deleted_at__isnull=True
        )
        context = {"carriers": carriers, "form": form}
        return render(request, self.template_name, context)


class CarrierDetailView(LoginRequiredMixin, View):
    template_name = "carrier/detail.html"

    def get(self, request, pk):
        carrier = get_object_or_404(
            Carrier.objects.select_related('tenant').prefetch_related(
                Prefetch(
                    'driver_set',
                    queryset=Driver.objects.annotate(
                        has_active_assignment=Exists(
                            DriverTruckAssignment.objects.filter(
                                driver=OuterRef('pk'),
                                start_date__lte=timezone.now(),
                                end_date__gt=timezone.now()
                            )
                        )
                    ).select_related('carrier', 'tenant')
                )
            ),
            pk=pk,
            tenant=request.user.profile.tenant
        )
        
        # Get active assignments
        now = timezone.now()
        active_assignments = DriverTruckAssignment.objects.filter(
            dispatch__carrier=carrier,
            start_date__lte=now,
            end_date__gt=now
        ).select_related('driver', 'truck')
        
        context = {
            "carrier": carrier,
            "active_assignments": active_assignments,
            "now": now
        }
        return render(request, self.template_name, context)


class CarrierCreateView(LoginRequiredMixin, View):
    template_name = "carrier/form.html"

    def get(self, request):
        form = CarrierForm()
        context = {"form": form, "action": "Create"}
        return render(request, self.template_name, context)

    def post(self, request):
        form = CarrierForm(request.POST)
        if form.is_valid():
            carrier = form.save(commit=False)
            carrier.tenant = request.user.profile.tenant
            carrier.save()
            messages.success(request, "Carrier created successfully!")
            return redirect("fleet:carrier-list")

        context = {"form": form, "action": "Create"}
        return render(request, self.template_name, context)


class CarrierUpdateView(LoginRequiredMixin, View):
    template_name = "carrier/form.html"

    def get(self, request, pk):
        carrier = get_object_or_404(
            Carrier.objects.select_related('tenant'),
            pk=pk,
            tenant=request.user.profile.tenant
        )
        form = CarrierForm(instance=carrier)
        context = {"form": form, "carrier": carrier, "action": "Update"}
        return render(request, self.template_name, context)

    def post(self, request, pk):
        carrier = get_object_or_404(
            Carrier.objects.select_related('tenant'),
            pk=pk,
            tenant=request.user.profile.tenant
        )
        form = CarrierForm(request.POST, instance=carrier)
        if form.is_valid():
            form.save()
            messages.success(request, "Carrier updated successfully!")
            return redirect("fleet:carrier-detail", pk=carrier.pk)

        context = {"form": form, "carrier": carrier, "action": "Update"}
        return render(request, self.template_name, context)


class CarrierDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            carrier = get_object_or_404(
                Carrier.objects.select_related('tenant'),
                pk=pk,
                tenant=request.user.profile.tenant,
                deleted_at__isnull=True  # Only get non-deleted carriers
            )
            
            # Check for active assignments
            active_assignments = DriverTruckAssignment.objects.filter(
                dispatch__carrier=carrier,
                start_date__lte=timezone.now(),
                end_date__gt=timezone.now()
            ).exists()
            
            if active_assignments:
                messages.error(request, f"Cannot delete carrier '{carrier.name}' because it has active assignments.")
                return redirect("fleet:carrier-detail", pk=carrier.pk)
            
            name = carrier.name
            # Soft delete instead of hard delete
            carrier.deleted_at = timezone.now()
            carrier.is_active = False
            carrier.save()
            
            messages.success(request, f"Carrier '{name}' deleted successfully!")
            return redirect("fleet:carrier-list")
            
        except Exception as e:
            messages.error(request, f"Error deleting carrier: {str(e)}")
            return redirect("fleet:carrier-list")


class CarrierOrganizationDetailView(View):
    def get(
        self, request, carrier_id, *args, **kwargs
    ):  # Make sure to include *args, **kwargs
        try:
            # Your logic to get carrier organization data
            carrier = Carrier.objects.get(id=carrier_id)
            org = Organization.objects.filter(
                carrier=carrier, tenant=request.user.profile.tenant
            ).first()

            if org:
                return JsonResponse(
                    {
                        "commission_percentage": org.commission_percentage,
                        "commission_currency": org.commission_currency,
                    }
                )
        except Carrier.DoesNotExist:
            # Handle the case where the carrier does not exist
            return JsonResponse(
                {
                    "commission_percentage": 12.0,  # Default value
                    "commission_currency": "CAD",  # Default value
                }
            )
