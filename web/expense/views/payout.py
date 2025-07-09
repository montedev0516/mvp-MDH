import logging
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, FormView, View
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Sum, Count
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import connection
import pandas as pd
import json
from datetime import datetime, timedelta
from decimal import Decimal

from expense.models import Payout, PayoutStatus, BVD, OtherExpense
from expense.forms.payout import (
    PayoutCalculationForm, PayoutUpdateForm, PayoutFilterForm, PayoutBulkActionForm
)

logger = logging.getLogger("django")


def check_column_exists(table_name, column_name):
    """Check if a column exists in the database table"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        """, [table_name, column_name])
        return cursor.fetchone()[0] > 0


class PayoutBaseView(LoginRequiredMixin):
    """Base view for Payout operations with common functionality"""
    model = Payout
    
    def get_queryset(self):
        """Get payouts for current tenant"""
        try:
            tenant = self.request.user.profile.tenant if hasattr(self.request.user, 'profile') else None
            if not tenant:
                return Payout.objects.none()  # Return empty queryset if no tenant
            
            return (
                Payout.objects.select_related("driver", "tenant")
                .prefetch_related("bvd_expenses", "other_expenses")
                .filter(tenant=tenant)
                .order_by("-from_date")
            )
        except AttributeError:
            return Payout.objects.none()  # Return empty queryset if no profile/tenant


class PayoutListView(PayoutBaseView, ListView):
    """List view for Payout records with filtering and bulk actions"""
    template_name = "expense/payout/list.html"
    context_object_name = "payouts"
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Apply filters
        driver_id = self.request.GET.get("driver")
        status = self.request.GET.get("status")
        from_date = self.request.GET.get("from_date")
        to_date = self.request.GET.get("to_date")
        search_query = self.request.GET.get("q")

        if driver_id:
            queryset = queryset.filter(driver_id=driver_id)
        
        if status:
            queryset = queryset.filter(status=status)
            
        if from_date:
            queryset = queryset.filter(from_date__date__gte=from_date)
            
        if to_date:
            queryset = queryset.filter(to_date__date__lte=to_date)
            
        if search_query:
            queryset = queryset.filter(
                Q(driver__first_name__icontains=search_query) |
                Q(driver__last_name__icontains=search_query) |
                Q(driver__email__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get tenant safely
        try:
            tenant = self.request.user.profile.tenant if hasattr(self.request.user, 'profile') else None
        except AttributeError:
            tenant = None
        
        # Add drivers for dropdown population
        if tenant:
            from fleet.models import Driver
            drivers = Driver.objects.filter(tenant=tenant, is_active=True).values('id', 'first_name', 'last_name')
            context["drivers"] = list(drivers)
        else:
            context["drivers"] = []
        
        # Add summary statistics with safe column checking
        queryset = self.get_queryset()
        
        # Check if the new columns exist before trying to aggregate them
        has_final_cad = check_column_exists('expense_payout', 'final_cad_amount')
        has_final_usd = check_column_exists('expense_payout', 'final_usd_amount')
        
        totals = {
            'total_payouts': queryset.count(),
            'draft_count': queryset.filter(status=PayoutStatus.DRAFT).count(),
            'processing_count': queryset.filter(status=PayoutStatus.PROCESSING).count(),
            'completed_count': queryset.filter(status=PayoutStatus.COMPLETED).count(),
        }
        
        # Only add amount totals if columns exist
        if has_final_cad:
            totals['total_cad_amount'] = queryset.aggregate(
                total=Sum("final_cad_amount")
            )['total'] or 0
        else:
            totals['total_cad_amount'] = 0
            
        if has_final_usd:
            totals['total_usd_amount'] = queryset.aggregate(
                total=Sum("final_usd_amount")
            )['total'] or 0
        else:
            totals['total_usd_amount'] = 0
        
        # Check for status synchronization issues in completed payouts
        completed_payouts = queryset.filter(status=PayoutStatus.COMPLETED)
        sync_issues_count = 0
        
        if completed_payouts.exists():
            try:
                for payout in completed_payouts[:10]:  # Check first 10 to avoid performance issues
                    sync_check = payout.check_and_fix_expense_status_sync(user=self.request.user, force_fix=False)
                    if sync_check['has_issues']:
                        sync_issues_count += 1
                        
                if sync_issues_count > 0:
                    messages.warning(
                        self.request,
                        f"Found {sync_issues_count} completed payouts with expense status synchronization issues. "
                        f"View individual payouts to automatically fix these issues."
                    )
            except Exception as e:
                logger.error(f"Error checking status synchronization: {str(e)}")
        
        context["totals"] = totals
        context["sync_issues_count"] = sync_issues_count
        
        # Add current query parameters for pagination links
        current_filters = {}
        for key in ['q', 'driver', 'status', 'from_date', 'to_date']:
            value = self.request.GET.get(key)
            if value:
                current_filters[key] = value
        context["current_filters"] = current_filters
        
        # Add a warning message if columns are missing
        if not has_final_cad or not has_final_usd:
            messages.warning(
                self.request, 
                "Database schema update required. Some payout calculations may not display correctly. "
                "Please contact your system administrator to run the database migration."
            )
        
        return context

    def post(self, request, *args, **kwargs):
        """Handle bulk actions"""
        bulk_form = PayoutBulkActionForm(request.POST)
        
        if bulk_form.is_valid():
            action = bulk_form.cleaned_data["action"]
            payout_ids = bulk_form.cleaned_data["payout_ids"]
            
            try:
                # Get tenant with error handling
                tenant = request.user.profile.tenant if hasattr(request.user, 'profile') else None
                if not tenant:
                    messages.error(request, "No tenant associated with user account")
                    return redirect("payout_list")
                
                payouts = Payout.objects.filter(
                    id__in=payout_ids,
                    tenant=tenant
                )
                
                if action == "mark_processing":
                    updated = 0
                    for payout in payouts.filter(status=PayoutStatus.DRAFT):
                        try:
                            payout.update_status(PayoutStatus.PROCESSING, request.user)
                            updated += 1
                        except ValidationError:
                            pass  # Skip invalid transitions
                    messages.success(request, f"Marked {updated} payouts as processing")
                    
                elif action == "mark_completed":
                    updated = 0
                    for payout in payouts.filter(status=PayoutStatus.PROCESSING):
                        try:
                            payout.update_status(PayoutStatus.COMPLETED, request.user)
                            updated += 1
                        except ValidationError:
                            pass  # Skip invalid transitions
                    messages.success(request, f"Marked {updated} payouts as completed")
                    
                elif action == "recalculate":
                    updated = 0
                    for payout in payouts.filter(status=PayoutStatus.DRAFT):
                        payout.calculate_totals()
                        payout.save()
                        updated += 1
                    messages.success(request, f"Recalculated {updated} payouts")
                    
                elif action == "export":
                    return self._export_payouts(payouts)
                    
            except Exception as e:
                messages.error(request, f"Error performing bulk action: {str(e)}")
        else:
            messages.error(request, "Invalid bulk action form")
            
        return redirect("payout_list")
    
    def _export_payouts(self, payouts):
        """Export payouts to Excel"""
        try:
            data = []
            for payout in payouts:
                data.append({
                    "Driver": str(payout.driver),
                    "From Date": payout.from_date.strftime("%Y-%m-%d"),
                    "To Date": payout.to_date.strftime("%Y-%m-%d"),
                    "Status": payout.get_status_display(),
                    "CAD Revenue": float(payout.cad_revenue),
                    "CAD Commission": float(payout.cad_commission),
                    "CAD Expenses": float(payout.cad_expenses),
                    "CAD Payout": float(payout.cad_payout),
                    "USD Revenue": float(payout.usd_revenue),
                    "USD Commission": float(payout.usd_commission),
                    "USD Expenses": float(payout.usd_expenses),
                    "USD Payout": float(payout.usd_payout),
                    "Exchange Rate": float(payout.exchange_rate),
                    "Final CAD": float(payout.final_cad_amount),
                    "Final USD": float(payout.final_usd_amount),
                    "Created": payout.created_at.strftime("%Y-%m-%d %H:%M"),
                })
            
            df = pd.DataFrame(data)
            
            response = HttpResponse(
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = 'attachment; filename="driver_payouts.xlsx"'
            
            df.to_excel(response, index=False, engine="openpyxl")
            return response
            
        except Exception as e:
            logger.error(f"Error exporting payouts: {str(e)}")
            messages.error(self.request, "Error exporting data. Please try again.")
            return redirect("payout_list")


class PayoutCalculateView(PayoutBaseView, FormView):
    """View for calculating new driver payouts"""
    template_name = "expense/payout/calculate.html"
    form_class = PayoutCalculationForm
    success_url = reverse_lazy("payout_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.profile.tenant
        return kwargs

    def form_valid(self, form):
        try:
            driver = form.cleaned_data["driver"]
            from_date = form.cleaned_data["from_date"]
            to_date = form.cleaned_data["to_date"]
            exchange_rate = form.cleaned_data.get("exchange_rate", 1.0000)
            
            # Create and calculate payout
            payout, calculation_result = Payout.create_for_driver_period(
                driver=driver,
                tenant=self.request.user.profile.tenant,
                from_date=from_date,
                to_date=to_date,
                exchange_rate=exchange_rate
            )
            
            messages.success(
                self.request, 
                f"Payout calculated successfully for {driver}! "
                f"CAD: ${calculation_result['final_cad_amount']:.2f}, "
                f"USD: ${calculation_result['final_usd_amount']:.2f}"
            )
            
            return redirect("payout_detail", pk=payout.pk)
            
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        except Exception as e:
            logger.error(f"Error calculating payout: {str(e)}")
            messages.error(self.request, "Error calculating payout. Please try again.")
            return self.form_invalid(form)


class PayoutDetailView(PayoutBaseView, DetailView):
    """Detail view for a Payout record"""
    template_name = "expense/payout/detail.html"
    context_object_name = "payout"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        payout = self.object
        
        # Check and fix status synchronization issues for completed payouts
        sync_result = None
        if payout.status == 'Completed':  # Use string value for comparison
            try:
                # First, check for issues without fixing
                sync_check = payout.check_and_fix_expense_status_sync(user=self.request.user, force_fix=False)
                
                # If issues found, automatically fix them
                if sync_check['has_issues']:
                    sync_result = payout.check_and_fix_expense_status_sync(user=self.request.user, force_fix=True)
                    
                    if sync_result['fixes_applied']:
                        messages.success(
                            self.request, 
                            f"Status synchronization: Fixed {len(sync_result['fixes_applied'])} expense status issues."
                        )
                    else:
                        messages.warning(
                            self.request,
                            f"Found {len(sync_result['issues_found'])} status synchronization issues that could not be automatically fixed."
                        )
                else:
                    sync_result = sync_check
                    
            except Exception as e:
                logger.error(f"Error during status sync check for payout {payout.pk}: {str(e)}")
                messages.warning(self.request, "Unable to verify expense status synchronization.")
        
        # Get related expenses (refresh from DB in case they were updated)
        bvd_expenses = payout.bvd_expenses.all()
        other_expenses = payout.other_expenses.all()
        
        # Get dispatches for this period
        from dispatch.models import Dispatch
        dispatches = Dispatch.objects.filter(
            driver=payout.driver,
            tenant=payout.tenant,
            status__in=['completed', 'delivered', 'invoiced', 'payment_received'],
            actual_end__range=[payout.from_date, payout.to_date]
        ).select_related('trip', 'order')
        
        context.update({
            "bvd_expenses": bvd_expenses,
            "other_expenses": other_expenses,
            "dispatches": dispatches,
            "sync_result": sync_result,  # Add sync result to context for debugging
            "expense_summary": {
                "bvd_count": bvd_expenses.count(),
                "other_count": other_expenses.count(),
                "dispatch_count": dispatches.count(),
                "bvd_total_cad": bvd_expenses.filter(currency='CAD').aggregate(
                    total=Sum('amount'))['total'] or 0,
                "bvd_total_usd": bvd_expenses.filter(currency='USD').aggregate(
                    total=Sum('amount'))['total'] or 0,
                "other_total_cad": other_expenses.filter(currency='CAD').aggregate(
                    total=Sum('amount'))['total'] or 0,
                "other_total_usd": other_expenses.filter(currency='USD').aggregate(
                    total=Sum('amount'))['total'] or 0,
            }
        })
        
        return context


class PayoutUpdateView(PayoutBaseView, UpdateView):
    """Update view for a Payout record"""
    form_class = PayoutUpdateForm
    template_name = "expense/payout/update.html"
    success_url = reverse_lazy("payout_list")

    def form_valid(self, form):
        try:
            payout = form.save(commit=False)
            payout.save()
            messages.success(self.request, "Payout updated successfully!")
            return redirect("payout_detail", pk=payout.pk)
        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)


class PayoutDeleteView(PayoutBaseView, DeleteView):
    """Delete view for a Payout record"""
    success_url = reverse_lazy("payout_list")

    def delete(self, request, *args, **kwargs):
        try:
            payout = self.get_object()
            if payout.status != PayoutStatus.DRAFT:
                messages.error(request, "Only draft payouts can be deleted")
                return redirect("payout_list")
                
            response = super().delete(request, *args, **kwargs)
            messages.success(request, "Payout deleted successfully!")
            return response
        except Exception as e:
            messages.error(request, f"Error deleting payout: {str(e)}")
            return redirect("payout_list")


class PayoutRecalculateView(PayoutBaseView, View):
    """View to recalculate a specific payout"""
    
    def post(self, request, pk):
        try:
            payout = get_object_or_404(
                Payout, 
                pk=pk, 
                tenant=request.user.profile.tenant
            )
            
            if payout.status != PayoutStatus.DRAFT:
                messages.error(request, "Only draft payouts can be recalculated")
                return redirect("payout_detail", pk=pk)
            
            calculation_result = payout.calculate_totals()
            payout.save()
            
            messages.success(
                request, 
                f"Payout recalculated successfully! "
                f"CAD: ${calculation_result['final_cad_amount']:.2f}, "
                f"USD: ${calculation_result['final_usd_amount']:.2f}"
            )
            
        except Exception as e:
            logger.error(f"Error recalculating payout: {str(e)}")
            messages.error(request, "Error recalculating payout. Please try again.")
        
        return redirect("payout_detail", pk=pk)


class PayoutCalculationAPIView(PayoutBaseView, View):
    """API view for AJAX payout calculation preview"""
    
    def post(self, request):
        try:
            # Parse JSON data
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError as e:
                return JsonResponse({
                    "success": False,
                    "error": f"Invalid JSON data: {str(e)}"
                }, status=400)
            
            # Validate required fields
            driver_id = data.get("driver_id")
            from_date_str = data.get("from_date")
            to_date_str = data.get("to_date")
            exchange_rate = data.get("exchange_rate", 1.0000)
            
            if not driver_id:
                return JsonResponse({
                    "success": False,
                    "error": "Driver ID is required"
                }, status=400)
                
            if not from_date_str or not to_date_str:
                return JsonResponse({
                    "success": False,
                    "error": "From date and to date are required"
                }, status=400)
            
            # Parse dates
            try:
                from_date = datetime.fromisoformat(from_date_str)
                to_date = datetime.fromisoformat(to_date_str)
            except ValueError as e:
                return JsonResponse({
                    "success": False,
                    "error": f"Invalid date format: {str(e)}"
                }, status=400)
            
            # Parse exchange rate
            try:
                exchange_rate = Decimal(str(exchange_rate))
            except (ValueError, TypeError) as e:
                return JsonResponse({
                    "success": False,
                    "error": f"Invalid exchange rate: {str(e)}"
                }, status=400)
            
            # Get driver
            try:
                from fleet.models import Driver
                driver = Driver.objects.get(
                    id=driver_id, 
                    tenant=request.user.profile.tenant
                )
            except Driver.DoesNotExist:
                return JsonResponse({
                    "success": False,
                    "error": "Driver not found or not accessible"
                }, status=404)
            
            # Create temporary payout for calculation (not saved to database)
            temp_payout = Payout(
                driver=driver,
                tenant=request.user.profile.tenant,
                from_date=from_date,
                to_date=to_date,
                exchange_rate=exchange_rate
            )
            
            # Calculate totals in preview mode (skips ManyToMany relationships)
            calculation_result = temp_payout.calculate_totals(preview_mode=True)
            
            return JsonResponse({
                "success": True,
                "data": {
                    key: float(value) if isinstance(value, Decimal) else value
                    for key, value in calculation_result.items()
                }
            })
            
        except Exception as e:
            logger.error(f"Error in payout calculation API: {str(e)}", exc_info=True)
            return JsonResponse({
                "success": False,
                "error": f"Calculation error: {str(e)}"
            }, status=500)


class PayoutSyncStatusView(PayoutBaseView, View):
    """View to manually trigger status synchronization for a payout"""
    
    def post(self, request, pk):
        try:
            payout = get_object_or_404(
                Payout, 
                pk=pk, 
                tenant=request.user.profile.tenant
            )
            
            if payout.status != PayoutStatus.COMPLETED:
                messages.error(request, "Status synchronization is only available for completed payouts")
                return redirect("payout_detail", pk=pk)
            
            # Check and fix status synchronization
            sync_result = payout.check_and_fix_expense_status_sync(user=request.user, force_fix=True)
            
            if sync_result['has_issues']:
                if sync_result['fixes_applied']:
                    messages.success(
                        request,
                        f"Status synchronization completed! Fixed {len(sync_result['fixes_applied'])} issues: "
                        f"{', '.join(sync_result['fixes_applied'])}"
                    )
                else:
                    messages.warning(
                        request,
                        f"Found {len(sync_result['issues_found'])} issues but could not fix them: "
                        f"{', '.join(sync_result['issues_found'])}"
                    )
            else:
                messages.info(request, "All expense statuses are already properly synchronized.")
            
        except Exception as e:
            logger.error(f"Error during manual status sync for payout {pk}: {str(e)}")
            messages.error(request, "Error during status synchronization. Please try again.")
        
        return redirect("payout_detail", pk=pk) 