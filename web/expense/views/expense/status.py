import logging
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.urls import reverse

from expense.models import BVD, OtherExpense, Payout, AccountPayableStatus, ReimbursementStatus, PayoutStatus

logger = logging.getLogger("django")


class StatusTransitionView(LoginRequiredMixin, View):
    """Handle status transitions for expenses and payouts"""
    
    def post(self, request, model_type, pk):
        """Handle status change requests"""
        try:
            # Get the model class
            model_map = {
                'bvd': BVD,
                'other': OtherExpense, 
                'payout': Payout
            }
            
            if model_type not in model_map:
                return JsonResponse({'error': 'Invalid model type'}, status=400)
                
            model_class = model_map[model_type]
            
            # Get the object
            obj = get_object_or_404(
                model_class, 
                pk=pk, 
                tenant=request.user.profile.tenant
            )
            
            # Get new status from request
            new_status = request.POST.get('new_status')
            status_type = request.POST.get('status_type', 'status')  # 'status' or 'reimbursement_status'
            
            if not new_status:
                return JsonResponse({'error': 'New status is required'}, status=400)
            
            # Handle different status types
            if status_type == 'reimbursement_status' and hasattr(obj, 'update_reimbursement_status'):
                # Handle reimbursement status for OtherExpense
                obj.update_reimbursement_status(new_status, request.user)
                status_display = obj.get_reimbursement_status_display()
                color_class = obj.get_reimbursement_status_color()
                
            elif hasattr(obj, 'update_status'):
                # Handle regular status for all models
                obj.update_status(new_status, request.user)
                status_display = obj.get_status_display()
                color_class = obj.get_status_color()
                
            else:
                return JsonResponse({'error': 'Status update not supported'}, status=400)
            
            # Success response for AJAX
            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'new_status': new_status,
                    'status_display': status_display,
                    'color_class': color_class,
                    'message': f'Status updated successfully to {status_display}'
                })
            
            # Success response for regular form submission
            messages.success(request, f'Status updated successfully to {status_display}')
            
            # Redirect back to the appropriate list view
            redirect_map = {
                'bvd': 'fuel_expense_bvd_list',
                'other': 'other_expense_list',
                'payout': 'payout_list'
            }
            
            return redirect(redirect_map.get(model_type, 'home'))
            
        except ValidationError as e:
            error_msg = str(e)
            
            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({'error': error_msg}, status=400)
            
            messages.error(request, error_msg)
            return redirect(request.META.get('HTTP_REFERER', 'home'))
            
        except Exception as e:
            logger.error(f"Error updating status: {str(e)}")
            error_msg = "An error occurred while updating the status"
            
            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({'error': error_msg}, status=500)
            
            messages.error(request, error_msg)
            return redirect(request.META.get('HTTP_REFERER', 'home'))


class StatusOptionsView(LoginRequiredMixin, View):
    """Get available status options for an object"""
    
    def get(self, request, model_type, pk):
        """Return available status transitions"""
        try:
            model_map = {
                'bvd': BVD,
                'other': OtherExpense,
                'payout': Payout
            }
            
            if model_type not in model_map:
                return JsonResponse({'error': 'Invalid model type'}, status=400)
                
            model_class = model_map[model_type]
            
            obj = get_object_or_404(
                model_class,
                pk=pk,
                tenant=request.user.profile.tenant
            )
            
            status_type = request.GET.get('status_type', 'status')
            
            if status_type == 'reimbursement_status' and hasattr(obj, 'get_next_reimbursement_status_options'):
                next_statuses = obj.get_next_reimbursement_status_options()
                choices = ReimbursementStatus.choices
            else:
                next_statuses = obj.get_next_status_options()
                if model_type == 'payout':
                    choices = PayoutStatus.choices
                else:
                    choices = AccountPayableStatus.choices
            
            # Build options list
            options = []
            for status_value, status_label in choices:
                if status_value in next_statuses:
                    options.append({
                        'value': status_value,
                        'label': status_label
                    })
            
            return JsonResponse({
                'success': True,
                'current_status': getattr(obj, status_type),
                'options': options
            })
            
        except Exception as e:
            logger.error(f"Error getting status options: {str(e)}")
            return JsonResponse({'error': 'Error getting status options'}, status=500) 