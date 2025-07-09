from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Exists, OuterRef, Q
from fleet.models.truck import Truck
from fleet.forms.truck import TruckForm
from dispatch.models import DriverTruckAssignment


class TruckListView(LoginRequiredMixin, View):
    template_name = "truck/list.html"

    def get(self, request):
        now = timezone.now()
        trucks = Truck.objects.filter(
            carrier__tenant=request.user.profile.tenant
        ).annotate(
            has_active_assignment=Exists(
                DriverTruckAssignment.objects.filter(
                    truck=OuterRef('pk'),
                    start_date__lte=now,
                    end_date__gt=now
                )
            )
        ).select_related('carrier')
        
        context = {
            "trucks": trucks,
            "form": TruckForm(tenant=request.user.profile.tenant),
            "now": now
        }
        return render(request, self.template_name, context)

    def post(self, request):
        form = TruckForm(request.POST, tenant=request.user.profile.tenant)
        if form.is_valid():
            truck = form.save(commit=False)
            truck.tenant = request.user.profile.tenant
            truck.save()
            messages.success(request, "Truck created successfully!")
            return redirect("fleet:truck-list")

        trucks = Truck.objects.filter(
            carrier__tenant=request.user.profile.tenant
        ).select_related('carrier')
        context = {"trucks": trucks, "form": form}
        return render(request, self.template_name, context)


class TruckDetailView(LoginRequiredMixin, View):
    template_name = "truck/detail.html"

    def get(self, request, pk):
        now = timezone.now()
        truck = get_object_or_404(
            Truck.objects.select_related('carrier').annotate(
                has_active_assignment=Exists(
                    DriverTruckAssignment.objects.filter(
                        truck=OuterRef('pk'),
                        start_date__lte=now,
                        end_date__gt=now
                    )
                )
            ),
            pk=pk,
            carrier__tenant=request.user.profile.tenant
        )
        
        # Get active assignments
        active_assignments = DriverTruckAssignment.objects.filter(
            truck=truck,
            start_date__lte=now,
            end_date__gt=now
        ).select_related('driver')
        
        context = {
            "truck": truck,
            "active_assignments": active_assignments,
            "now": now
        }
        return render(request, self.template_name, context)


class TruckCreateView(LoginRequiredMixin, View):
    template_name = "truck/form.html"

    def get(self, request):
        form = TruckForm(tenant=request.user.profile.tenant)
        context = {"form": form, "action": "Create"}
        return render(request, self.template_name, context)

    def post(self, request):
        form = TruckForm(request.POST, tenant=request.user.profile.tenant)
        if form.is_valid():
            truck = form.save(commit=False)
            truck.tenant = request.user.profile.tenant
            truck.save()
            messages.success(request, "Truck created successfully!")
            return redirect("fleet:truck-list")

        context = {"form": form, "action": "Create"}
        return render(request, self.template_name, context)


class TruckUpdateView(LoginRequiredMixin, View):
    template_name = "truck/form.html"

    def get(self, request, pk):
        truck = get_object_or_404(
            Truck.objects.select_related('carrier'),
            pk=pk,
            carrier__tenant=request.user.profile.tenant
        )
        form = TruckForm(instance=truck, tenant=request.user.profile.tenant)
        context = {"form": form, "truck": truck, "action": "Update"}
        return render(request, self.template_name, context)

    def post(self, request, pk):
        truck = get_object_or_404(
            Truck.objects.select_related('carrier'),
            pk=pk,
            carrier__tenant=request.user.profile.tenant
        )
        form = TruckForm(request.POST, instance=truck, tenant=request.user.profile.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Truck updated successfully!")
            return redirect("fleet:truck-detail", pk=truck.pk)

        context = {"form": form, "truck": truck, "action": "Update"}
        return render(request, self.template_name, context)


class TruckDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        truck = get_object_or_404(
            Truck.objects.select_related('carrier'),
            pk=pk,
            carrier__tenant=request.user.profile.tenant
        )
        identifier = f"{truck.unit} ({truck.make} {truck.model})"
        truck.delete()
        messages.success(request, f"Truck '{identifier}' deleted successfully!")
        return redirect("fleet:truck-list")
