from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from fleet.models import Driver, Truck, Carrier
from dispatch.models import (
    DriverTruckAssignment,
    AssignmentStatus,
    Dispatch,
    DispatchStatus
)
from dispatch.forms import AssignmentForm
import logging

logger = logging.getLogger(__name__)

class AssignmentListView(LoginRequiredMixin, ListView):
    model = DriverTruckAssignment
    template_name = 'assignment/list.html'
    context_object_name = 'assignments'
    ordering = ['-created_at']
    paginate_by = 20

    def get_queryset(self):
        """Get assignments filtered by tenant and search criteria."""
        queryset = DriverTruckAssignment.objects.filter(
            tenant=self.request.user.profile.tenant
        ).select_related(
            'driver',
            'truck',
            'dispatch',
            'dispatch__order'
        )

        # Add search functionality
        search_query = self.request.GET.get('q')
        if search_query:
            queryset = queryset.filter(
                Q(driver__first_name__icontains=search_query) |
                Q(driver__last_name__icontains=search_query) |
                Q(truck__unit__icontains=search_query) |
                Q(dispatch__order__order_number__icontains=search_query)
            )

        # Add status filter
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = AssignmentStatus.choices
        context['search_query'] = self.request.GET.get('q', '')
        context['status_filter'] = self.request.GET.get('status', '')
        return context


class AssignmentDetailView(LoginRequiredMixin, DetailView):
    model = DriverTruckAssignment
    template_name = 'assignment/detail.html'
    context_object_name = 'assignment'

    def get_queryset(self):
        return DriverTruckAssignment.objects.filter(
            tenant=self.request.user.profile.tenant
        ).select_related(
            'driver',
            'truck',
            'dispatch',
            'dispatch__order'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignment = self.get_object()

        # Add dispatch information if available
        if assignment.dispatch:
            context['dispatch'] = assignment.dispatch
            context['order'] = assignment.dispatch.order

        # Check if assignment is in final state
        context['is_final'] = assignment.status in [
            AssignmentStatus.OFF_DUTY,
            AssignmentStatus.CANCELLED
        ]

        return context


@method_decorator(login_required, name='dispatch')
class AssignmentCreateView(LoginRequiredMixin, CreateView):
    model = DriverTruckAssignment
    form_class = AssignmentForm
    template_name = 'assignment/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        tenant = self.request.user.profile.tenant
        
        logger.info(f"[AssignmentCreateView.get_form_kwargs] Starting get_form_kwargs")
        logger.info(f"[AssignmentCreateView.get_form_kwargs] User ID: {self.request.user.id}")
        logger.info(f"[AssignmentCreateView.get_form_kwargs] User Profile: {self.request.user.profile}")
        logger.info(f"[AssignmentCreateView.get_form_kwargs] Tenant: {tenant}")
        
        kwargs['tenant'] = tenant
        
        # If dispatch_id is in GET parameters, get the dispatch instance
        dispatch_id = self.request.GET.get('dispatch')
        if dispatch_id:
            try:
                dispatch = Dispatch.objects.get(
                    id=dispatch_id,
                    tenant=tenant
                )
                kwargs['dispatch'] = dispatch
                logger.info(f"[AssignmentCreateView.get_form_kwargs] Found dispatch: {dispatch.id}")
            except Dispatch.DoesNotExist:
                logger.warning(f"[AssignmentCreateView.get_form_kwargs] Dispatch not found: {dispatch_id}")
            except Exception as e:
                logger.error(f"[AssignmentCreateView.get_form_kwargs] Error getting dispatch: {str(e)}", exc_info=True)
        
        logger.info(f"[AssignmentCreateView.get_form_kwargs] Final kwargs: {kwargs}")
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        logger.info(f"[AssignmentCreateView.get_initial] Starting get_initial")
        
        # If dispatch is specified in GET parameters, set it as initial
        dispatch_id = self.request.GET.get('dispatch')
        if dispatch_id:
            try:
                dispatch = Dispatch.objects.get(
                    id=dispatch_id,
                    tenant=self.request.user.profile.tenant
                )
                initial['dispatch'] = dispatch
               
                logger.info(f"[AssignmentCreateView.get_initial] Set initial data from dispatch: {initial}")
            except Dispatch.DoesNotExist:
                logger.warning(f"[AssignmentCreateView.get_initial] Dispatch not found: {dispatch_id}")
            except Exception as e:
                logger.error(f"[AssignmentCreateView.get_initial] Error setting initial data: {str(e)}", exc_info=True)
        
        logger.info(f"[AssignmentCreateView.get_initial] Final initial data: {initial}")
        return initial

    def get_success_url(self):
        return reverse_lazy('dispatch:assignment-detail', kwargs={'pk': self.object.pk})

    def post(self, request, *args, **kwargs):
        """Override post to add logging"""
        logger.info(f"[AssignmentCreateView.post] POST data: {request.POST}")
        logger.info(f"[AssignmentCreateView.post] Files: {request.FILES}")
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        """Override form_invalid to add logging"""
        logger.error(f"[AssignmentCreateView.form_invalid] Form errors: {form.errors}")
        logger.error(f"[AssignmentCreateView.form_invalid] Form data: {form.data}")
        for field in form:
            logger.error(f"[AssignmentCreateView.form_invalid] Field {field.name}: value={field.value()}, errors={field.errors}")
        
        # Add form errors to messages
        for field, errors in form.errors.items():
            if field == '__all__':  # Non-field errors
                for error in errors:
                    messages.error(self.request, error)
            else:
                for error in errors:
                    messages.error(self.request, f"{field}: {error}")
        
        return super().form_invalid(form)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                logger.info(f"[AssignmentCreateView.form_valid] Form data: {form.cleaned_data}")
                
                # Get the driver and truck from the cleaned data
                driver = form.cleaned_data.get('driver')
                truck = form.cleaned_data.get('truck')
                
                logger.info(f"[AssignmentCreateView.form_valid] Driver from form: {driver}")
                logger.info(f"[AssignmentCreateView.form_valid] Truck from form: {truck}")
                
                if not driver or not truck:
                    if not driver:
                        form.add_error('driver', 'Driver is required')
                    if not truck:
                        form.add_error('truck', 'Truck is required')
                    return self.form_invalid(form)
                
                # First save without commit to get the instance
                assignment = form.save(commit=False)
                
                # Set additional fields
                assignment.tenant = self.request.user.profile.tenant
                assignment.created_by = self.request.user
                
                # Log assignment state
                logger.info(f"[AssignmentCreateView.form_valid] Assignment before save: driver={assignment.driver_id}, truck={assignment.truck_id}, status={assignment.status}")

                # Validate driver and truck availability
                if not self.is_resource_available(assignment):
                    form.add_error(None, "Selected driver or truck is not available for this time period")
                    return self.form_invalid(form)

                # Save the assignment
                assignment.save()
                logger.info(f"[AssignmentCreateView.form_valid] Assignment saved with ID: {assignment.id}")

                # Sync driver and truck status
                assignment.sync_driver_truck_status()

                messages.success(self.request, "Assignment created successfully!")
                return super().form_valid(form)

        except Exception as e:
            logger.error(f"[AssignmentCreateView.form_valid] Error creating assignment: {str(e)}", exc_info=True)
            form.add_error(None, f"Error creating assignment: {str(e)}")
            return self.form_invalid(form)

    def is_resource_available(self, assignment):
        """Check if driver and truck are available for the assignment period."""
        if not assignment.end_date:
            assignment.end_date = assignment.start_date + timezone.timedelta(days=365)

        # Check for conflicting assignments
        conflicting_assignments = DriverTruckAssignment.objects.filter(
            Q(driver=assignment.driver) | Q(truck=assignment.truck),
            tenant=assignment.tenant,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
            start_date__lt=assignment.end_date,
            end_date__gt=assignment.start_date
        )

        # Exclude current instance if updating
        if assignment.pk:
            conflicting_assignments = conflicting_assignments.exclude(pk=assignment.pk)

        return not conflicting_assignments.exists()


class AssignmentUpdateView(LoginRequiredMixin, UpdateView):
    model = DriverTruckAssignment
    form_class = AssignmentForm
    template_name = 'assignment/form.html'
    context_object_name = 'assignment'

    def get_queryset(self):
        return DriverTruckAssignment.objects.filter(
            tenant=self.request.user.profile.tenant
        ).select_related(
            'driver',
            'truck',
            'dispatch'
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tenant'] = self.request.user.profile.tenant
        return kwargs

    def get_success_url(self):
        return reverse_lazy('dispatch:assignment-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        try:
            with transaction.atomic():
                assignment = form.save(commit=False)
                old_status = self.get_object().status
                new_status = form.cleaned_data.get('status')

                # Validate status transition
                if old_status != new_status:
                    try:
                        assignment.validate_status_transition(new_status)
                    except ValidationError as e:
                        messages.error(self.request, str(e))
                        return self.form_invalid(form)

                # Validate resource availability if dates changed
                if (form.cleaned_data.get('start_date') != assignment.start_date or
                    form.cleaned_data.get('end_date') != assignment.end_date):
                    if not self.is_resource_available(assignment):
                        raise ValidationError("Selected driver or truck is not available for this period")

                # Save the assignment
                assignment.save()

                # Sync driver and truck status
                assignment.sync_driver_truck_status()

                messages.success(self.request, 'Assignment updated successfully.')
                return super().form_valid(form)

        except ValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        except Exception as e:
            logger.error(f"Error updating assignment: {str(e)}")
            messages.error(self.request, f"Error updating assignment: {str(e)}")
            return self.form_invalid(form)

    def is_resource_available(self, assignment):
        """Check if driver and truck are available for the assignment period."""
        start_date = assignment.start_date or timezone.now()
        end_date = assignment.end_date

        # Check for conflicting assignments
        conflicting_assignments = DriverTruckAssignment.objects.filter(
            Q(driver=assignment.driver) | Q(truck=assignment.truck),
            tenant=self.request.user.profile.tenant,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
            start_date__lt=end_date if end_date else timezone.now() + timezone.timedelta(days=365),
            end_date__gt=start_date
        ).exclude(pk=assignment.pk)

        return not conflicting_assignments.exists()

    def update_dispatch_status(self, dispatch, assignment_status):
        """Update dispatch status based on assignment status change."""
        if assignment_status == AssignmentStatus.ON_DUTY:
            dispatch.status = DispatchStatus.IN_TRANSIT
        elif assignment_status == AssignmentStatus.OFF_DUTY:
            dispatch.status = DispatchStatus.COMPLETED
        elif assignment_status == AssignmentStatus.CANCELLED:
            dispatch.status = DispatchStatus.CANCELLED
        
        dispatch.save()


class AssignmentDeleteView(LoginRequiredMixin, DeleteView):
    model = DriverTruckAssignment
    template_name = 'assignment/confirm_delete.html'
    success_url = reverse_lazy('dispatch:assignment-list')

    def get_queryset(self):
        return DriverTruckAssignment.objects.filter(
            tenant=self.request.user.profile.tenant
        )

    def delete(self, request, *args, **kwargs):
        try:
            assignment = self.get_object()
            
            # Check if assignment can be deleted
            if assignment.status not in [AssignmentStatus.PENDING, AssignmentStatus.CANCELLED]:
                messages.error(request, "Cannot delete active or completed assignments")
                return self.handle_error()

            # Release resources
            driver = assignment.driver
            truck = assignment.truck
            
            driver.duty_status = 'AVAILABLE'
            truck.duty_status = 'AVAILABLE'
            
            driver.save()
            truck.save()

            # Delete the assignment
            response = super().delete(request, *args, **kwargs)
            messages.success(request, 'Assignment deleted successfully.')
            return response

        except Exception as e:
            logger.error(f"Error deleting assignment: {str(e)}")
            messages.error(request, f"Error deleting assignment: {str(e)}")
            return self.handle_error()

    def handle_error(self):
        return redirect('dispatch:assignment-detail', pk=self.get_object().pk)


@login_required
@require_GET
def get_dispatch_details(request):
    """
    AJAX view to get dispatch details and update form fields.
    When a dispatch is selected, only show the driver and truck assigned to that dispatch.
    """
    try:
        dispatch_id = request.GET.get('dispatch_id')
        if not dispatch_id:
            return JsonResponse({'error': 'No dispatch ID provided'}, status=400)

        # Get the dispatch with related data
        dispatch = Dispatch.objects.select_related(
            'trip',
            'driver',
            'driver__carrier',
            'truck',
            'truck__carrier',
            'carrier',
            'order'
        ).get(
            id=dispatch_id,
            tenant=request.user.profile.tenant
        )

        # Validate dispatch status - only allow assignments for active dispatches
        if dispatch.status in [DispatchStatus.COMPLETED, DispatchStatus.CANCELLED]:
            return JsonResponse({
                'error': f'Cannot create assignment for {dispatch.get_status_display().lower()} dispatch'
            }, status=400)

        # Check if dispatch already has an active assignment
        existing_assignment = DriverTruckAssignment.objects.filter(
            dispatch=dispatch,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
            tenant=request.user.profile.tenant
        ).first()

        if existing_assignment:
            return JsonResponse({
                'error': f'Dispatch already has an active assignment (ID: {existing_assignment.id})'
            }, status=400)

        # Get order dates for validation
        pickup_date = dispatch.order.pickup_date if dispatch.order else None
        delivery_date = dispatch.order.delivery_date if dispatch.order else None

        # Format dates for display and form
        pickup_date_str = pickup_date.strftime('%Y-%m-%dT%H:%M') if pickup_date else None
        delivery_date_str = delivery_date.strftime('%Y-%m-%dT%H:%M') if delivery_date else None

        # Check if dispatch has assigned driver and truck
        if not dispatch.driver or not dispatch.truck:
            return JsonResponse({
                'error': 'Dispatch must have both driver and truck assigned before creating assignment'
            }, status=400)

        # Validate that the assigned driver and truck are available
        start_check = pickup_date or timezone.now()
        end_check = delivery_date or (start_check + timezone.timedelta(days=1))

        # Check for conflicting driver assignments
        conflicting_driver_assignments = DriverTruckAssignment.objects.filter(
            driver=dispatch.driver,
            tenant=request.user.profile.tenant,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
            start_date__lt=end_check,
            end_date__gt=start_check
        ).exclude(dispatch=dispatch)

        if conflicting_driver_assignments.exists():
            conflicting_assignment = conflicting_driver_assignments.first()
            return JsonResponse({
                'error': f'Driver {dispatch.driver.first_name} {dispatch.driver.last_name} is already assigned to another dispatch during this period (Assignment ID: {conflicting_assignment.id})'
            }, status=400)

        # Check for conflicting truck assignments
        conflicting_truck_assignments = DriverTruckAssignment.objects.filter(
            truck=dispatch.truck,
            tenant=request.user.profile.tenant,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
            start_date__lt=end_check,
            end_date__gt=start_check
        ).exclude(dispatch=dispatch)

        if conflicting_truck_assignments.exists():
            conflicting_assignment = conflicting_truck_assignments.first()
            return JsonResponse({
                'error': f'Truck {dispatch.truck.unit} is already assigned to another dispatch during this period (Assignment ID: {conflicting_assignment.id})'
            }, status=400)

        # Only return the specific driver and truck assigned to this dispatch
        available_drivers = [{
            'id': dispatch.driver.id,
            'first_name': dispatch.driver.first_name,
            'last_name': dispatch.driver.last_name,
            'carrier': dispatch.driver.carrier.name if dispatch.driver.carrier else 'No Carrier'
        }]

        available_trucks = [{
            'id': dispatch.truck.id,
            'unit': dispatch.truck.unit,
            'model': f"{dispatch.truck.make} {dispatch.truck.model}" if dispatch.truck.make and dispatch.truck.model else dispatch.truck.model or 'Unknown Model'
        }]

        # Prepare the response data
        response_data = {
            'success': True,
            'dispatch': {
                'id': dispatch.id,
                'order_number': dispatch.order.order_number if dispatch.order else None,
                'driver_name': f"{dispatch.driver.first_name} {dispatch.driver.last_name}",
                'truck_unit': f"{dispatch.truck.unit} ({dispatch.truck.make} {dispatch.truck.model})" if dispatch.truck.make and dispatch.truck.model else dispatch.truck.unit,
                'carrier_name': dispatch.carrier.name if dispatch.carrier else 'No Carrier',
                'start_date': pickup_date_str,
                'end_date': delivery_date_str,
                'status': dispatch.get_status_display(),
                'status_color': {
                    'Pending': 'warning',
                    'Assigned': 'primary',
                    'In Transit': 'info',
                    'Delivered': 'success',
                    'Invoiced': 'warning',
                    'Payment Received': 'success',
                    'Completed': 'dark',
                    'Cancelled': 'danger'
                }.get(dispatch.get_status_display(), 'secondary')
            },
            'available_drivers': available_drivers,
            'available_trucks': available_trucks,
            'selected_driver': dispatch.driver.id,
            'selected_truck': dispatch.truck.id,
            'status': AssignmentStatus.ASSIGNED,
            'date_constraints': {
                'min_start_date': pickup_date_str,
                'max_end_date': delivery_date_str,
                'pickup_date': pickup_date_str,
                'delivery_date': delivery_date_str
            },
            'validation_info': {
                'dispatch_status': dispatch.status,
                'has_existing_assignment': False,
                'driver_available': True,
                'truck_available': True
            }
        }

        return JsonResponse(response_data)

    except Dispatch.DoesNotExist:
        return JsonResponse({'error': 'Dispatch not found'}, status=404)
    except Exception as e:
        logger.error(f"Error getting dispatch details: {str(e)}", exc_info=True)
        return JsonResponse({'error': f'Internal server error: {str(e)}'}, status=500) 