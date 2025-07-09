import logging
from django.views.generic import ListView, UpdateView, DeleteView, DetailView, View
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError
import pandas as pd
from expense.models import OtherExpense
from expense.forms import OtherExpenseForm

logger = logging.getLogger("django")


class OtherExpenseBaseView(LoginRequiredMixin):
    """Base view for Other Expense operations with common functionality"""
    model = OtherExpense
    
    def get_queryset(self):
        """Get expenses for current tenant"""
        return (
            OtherExpense.objects.select_related("truck", "driver", "tenant")
            .filter(tenant=self.request.user.profile.tenant)
            .order_by("-date")
        )


class OtherExpenseListView(OtherExpenseBaseView, ListView):
    """List view for Other Expense records with search and filter capabilities"""
    template_name = "expense/other/list.html"
    context_object_name = "expenses"

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Get search parameters
        search_query = self.request.GET.get("q")
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        category = self.request.GET.get("category")
        status = self.request.GET.get("status")
        truck = self.request.GET.get("truck")
        reimbursement_status = self.request.GET.get("reimbursement_status")

        # Apply filters
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query)
                | Q(description__icontains=search_query)
                | Q(vendor_name__icontains=search_query)
                | Q(vendor_location__icontains=search_query)
                | Q(receipt_number__icontains=search_query)
            )

        if start_date:
            queryset = queryset.filter(date__date__gte=start_date)

        if end_date:
            queryset = queryset.filter(date__date__lte=end_date)

        if category:
            queryset = queryset.filter(category=category)

        if status:
            queryset = queryset.filter(status=status)

        if truck:
            queryset = queryset.filter(truck_id=truck)

        if reimbursement_status:
            queryset = queryset.filter(reimbursement_status=reimbursement_status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = OtherExpenseForm(tenant=self.request.user.profile.tenant)
        
        # Add summary statistics
        queryset = self.get_queryset()
        
        # Calculate currency-specific totals with proper defaults
        cad_total = queryset.filter(currency='CAD').aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        usd_total = queryset.filter(currency='USD').aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        # Calculate status counts
        pending_count = queryset.filter(status='Pending').count()
        approved_count = queryset.filter(status='Approved').count()
        reimbursed_count = queryset.filter(status='Reimbursed').count()
        
        context.update({
            "record_count": queryset.count(),
            "cad_total": cad_total,
            "usd_total": usd_total,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "reimbursed_count": reimbursed_count,
            "search_query": self.request.GET.get("q", ""),
            "start_date": self.request.GET.get("start_date", ""),
            "end_date": self.request.GET.get("end_date", ""),
            "selected_category": self.request.GET.get("category", ""),
            "selected_status": self.request.GET.get("status", ""),
            "selected_truck": self.request.GET.get("truck", ""),
            "selected_reimbursement_status": self.request.GET.get("reimbursement_status", ""),
        })
        
        # Add filter preservation for pagination
        current_filters = {}
        for key, value in self.request.GET.items():
            if key != 'page' and value:
                current_filters[key] = value
        context['current_filters'] = current_filters
        
        return context

    def post(self, request, *args, **kwargs):
        form = OtherExpenseForm(
            request.POST,
            request.FILES,
            tenant=request.user.profile.tenant
        )
        
        if form.is_valid():
            expense = form.save(commit=False)
            expense.tenant = request.user.profile.tenant
            expense.save()
            messages.success(request, "Expense created successfully!")
        else:
            messages.error(request, "Error creating expense. Please check the form.")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
                    
        return self.get(request, *args, **kwargs)


class OtherExpenseDetailView(OtherExpenseBaseView, DetailView):
    """Detail view for an Other Expense record"""
    template_name = "expense/other/detail.html"
    context_object_name = "expense"


class OtherExpenseUpdateView(OtherExpenseBaseView, UpdateView):
    """Update view for an Other Expense record"""
    form_class = OtherExpenseForm
    template_name = "expense/other/update.html"
    context_object_name = "expense"
    success_url = reverse_lazy("other_expense_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.profile.tenant
        return kwargs

    def form_valid(self, form):
        try:
            expense = form.save(commit=False)
            expense.tenant = self.request.user.profile.tenant
            expense.save()
            messages.success(self.request, "Expense updated successfully!")
            return redirect(self.success_url)
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)


class OtherExpenseDeleteView(OtherExpenseBaseView, DeleteView):
    """Delete view for an Other Expense record"""
    success_url = reverse_lazy("other_expense_list")

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, "Expense deleted successfully!")
            return response
        except Exception as e:
            messages.error(request, f"Error deleting expense: {str(e)}")
            return redirect("other_expense_list")


class OtherExpenseExportView(OtherExpenseBaseView, View):
    """Export view for Other Expense records to Excel"""
    
    def get(self, request, *args, **kwargs):
        try:
            # Get filtered queryset
            queryset = self.get_queryset()
            
            # Create DataFrame
            data = []
            for expense in queryset:
                row = {
                    "Date": expense.date.strftime("%Y-%m-%d %H:%M"),
                    "Name": expense.name,
                    "Category": expense.get_category_display(),
                    "Description": expense.description,
                    "Amount": expense.amount,
                    "Currency": expense.currency,
                    "Tax Amount": expense.tax_amount,
                    "Tax Type": expense.get_tax_type_display(),
                    "Vendor": expense.vendor_name,
                    "Location": expense.vendor_location,
                    "Receipt #": expense.receipt_number,
                    "Payment Method": expense.get_payment_method_display(),
                    "Payment Reference": expense.payment_reference,
                    "Status": expense.get_status_display(),
                    "Reimbursement Status": expense.get_reimbursement_status_display(),
                    "Driver": str(expense.driver),
                    "Truck": str(expense.truck),
                    "Notes": expense.notes,
                    "Created At": expense.created_at.strftime("%Y-%m-%d %H:%M"),
                }
                data.append(row)

            # Convert to DataFrame
            df = pd.DataFrame(data)

            # Create response
            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = 'attachment; filename="other_expenses.xlsx"'

            # Write to Excel
            df.to_excel(response, index=False, engine="openpyxl")

            return response

        except Exception as e:
            logger.error(f"Error exporting expense data: {str(e)}")
            messages.error(request, "Error exporting data. Please try again.")
            return redirect("other_expense_list")
