from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from fleet.models import Customer
from customer.forms import CustomerForm


class CustomerListView(LoginRequiredMixin, View):
    def get(self, request):
        customers = Customer.objects.filter(tenant=request.user.profile.tenant)
        form = CustomerForm()
        return render(
            request, "customers/list.html", {"customers": customers, "form": form}
        )

    def post(self, request):
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.tenant = request.user.profile.tenant
            customer.save()
            messages.success(request, "Customer created successfully!")
            return redirect("customer_list")

        customers = Customer.objects.filter(tenant=request.user.profile.tenant)
        return render(
            request, "customers/list.html", {"customers": customers, "form": form}
        )


class CustomerDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        customer = get_object_or_404(
            Customer, pk=pk, tenant=request.user.profile.tenant
        )
        return render(request, "customers/detail.html", {"customer": customer})


class CustomerUpdateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        customer = get_object_or_404(
            Customer, pk=pk, tenant=request.user.profile.tenant
        )
        form = CustomerForm(instance=customer)
        return render(
            request, "customers/edit.html", {"form": form, "customer": customer}
        )

    def post(self, request, pk):
        customer = get_object_or_404(
            Customer, pk=pk, tenant=request.user.profile.tenant
        )
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.tenant = request.user.profile.tenant
            customer.save()
            messages.success(request, "Customer updated successfully!")
            return redirect("customer_detail", pk=customer.pk)

        return render(
            request, "customers/edit.html", {"form": form, "customer": customer}
        )


class CustomerDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        customer = get_object_or_404(
            Customer, pk=pk, tenant=request.user.profile.tenant
        )
        customer.delete()
        messages.success(request, "Customer deleted successfully!")
        return redirect("customer_list")


class CustomerCreateView(LoginRequiredMixin, View):
    def get(self, request):
        form = CustomerForm()
        return render(request, "customers/create.html", {"form": form})

    def post(self, request):
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.tenant = request.user.profile.tenant
            customer.save()
            messages.success(request, "Customer created successfully!")
            return redirect("customer_list")
        return render(request, "customers/create.html", {"form": form})


def get_customer_form(request, *args, **kwargs):
    """Helper function to get a form with tenant-filtered querysets"""
    form = CustomerForm(*args, **kwargs)
    # Filter any querysets in the form by tenant
    for field in form.fields.values():
        if hasattr(field, "queryset"):
            field.queryset = field.queryset.filter(tenant=request.user.profile.tenant)
    return form
