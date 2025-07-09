from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q
from dispatch.models import (
    DriverTruckAssignment, 
    AssignmentStatus,
    Dispatch,
    DispatchStatus
)
from fleet.models import Driver, Truck
import logging
from django.db import connection

logger = logging.getLogger(__name__)

class AssignmentForm(forms.ModelForm):
    """Form for creating and updating driver-truck assignments."""

    driver = forms.ModelChoiceField(
        queryset=Driver.objects.none(),
        required=True,
        error_messages={
            'required': 'Please select a driver',
            'invalid_choice': 'Please select a valid driver'
        },
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Driver",
            "id": "id_driver"
        })
    )
    
    truck = forms.ModelChoiceField(
        queryset=Truck.objects.none(),
        required=True,
        error_messages={
            'required': 'Please select a truck',
            'invalid_choice': 'Please select a valid truck'
        },
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Truck",
            "id": "id_truck"
        })
    )
    
    dispatch = forms.ModelChoiceField(
        queryset=Dispatch.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Dispatch",
            "id": "id_dispatch",
            "hx-get": "/dispatch/assignment/get-dispatch-details/",
            "hx-trigger": "change",
            "hx-target": "#assignment-form",
            "hx-swap": "none"
        })
    )
    
    start_date = forms.DateTimeField(
        required=True,
        error_messages={
            'required': 'Please specify a start date and time'
        },
        widget=forms.DateTimeInput(
            attrs={
                "class": "form-control",
                "type": "datetime-local"
            },
            format="%Y-%m-%dT%H:%M"
        ),
        initial=timezone.now
    )
    
    end_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                "class": "form-control",
                "type": "datetime-local"
            },
            format="%Y-%m-%dT%H:%M"
        )
    )
    
    status = forms.ChoiceField(
        choices=AssignmentStatus.choices,
        required=True,
        initial=AssignmentStatus.ASSIGNED,
        error_messages={
            'required': 'Please select a status',
            'invalid_choice': 'Please select a valid status'
        },
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_status"
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Enter any additional notes here..."
        })
    )
    
    odometer_start = forms.IntegerField(
        required=True,
        error_messages={
            'required': 'Please enter the starting odometer reading'
        },
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "placeholder": "Starting odometer reading"
        })
    )
    
    odometer_end = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "placeholder": "Ending odometer reading"
        })
    )

    class Meta:
        model = DriverTruckAssignment
        fields = [
            "driver",
            "truck",
            "dispatch",
            "start_date",
            "end_date",
            "status",
            "notes",
            "odometer_start",
            "odometer_end",
        ]

    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop("tenant", None)
        self.dispatch_instance = kwargs.pop("dispatch", None)
        
        logger.info(f"[AssignmentForm.__init__] Starting form initialization")
        logger.info(f"[AssignmentForm.__init__] Tenant ID: {self.tenant.id if self.tenant else None}")
        
        super().__init__(*args, **kwargs)
        
        if not self.tenant:
            logger.error("[AssignmentForm.__init__] No tenant provided!")
            return
            
        try:
            # First get all trucks and check their status
            all_trucks = Truck.objects.filter(tenant=self.tenant)
            logger.info(f"[AssignmentForm.__init__] All trucks for tenant: {all_trucks.count()}")
            
            # Log status values in database
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT status, COUNT(*) 
                    FROM fleet_truck 
                    WHERE tenant_id = %s 
                    GROUP BY status
                """, [self.tenant.id])
                status_counts = cursor.fetchall()
                logger.info(f"[AssignmentForm.__init__] Truck status distribution: {status_counts}")
                
                cursor.execute("""
                    SELECT DISTINCT duty_status, COUNT(*) 
                    FROM fleet_truck 
                    WHERE tenant_id = %s 
                    GROUP BY duty_status
                """, [self.tenant.id])
                duty_status_counts = cursor.fetchall()
                logger.info(f"[AssignmentForm.__init__] Truck duty_status distribution: {duty_status_counts}")
            
            # Log each truck's details
            for truck in all_trucks:
                logger.info(
                    f"Truck {truck.id} ({truck.unit}): "
                    f"status={truck.status}, "
                    f"duty_status={truck.duty_status}"
                )
            
            # Try different status values
            active_trucks = all_trucks.filter(status__in=['ACTIVE', 'active', 'Active'])
            logger.info(f"[AssignmentForm.__init__] Trucks with any active status: {active_trucks.count()}")
            
            available_trucks = active_trucks.filter(duty_status__in=['AVAILABLE', 'available', 'Available'])
            logger.info(f"[AssignmentForm.__init__] Available trucks: {available_trucks.count()}")
            
            # Get current assignments
            current_assignments = DriverTruckAssignment.objects.filter(
                tenant=self.tenant,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                end_date__isnull=True
            )
            
            # Log assignments
            logger.info(f"[AssignmentForm.__init__] Current assignments: {current_assignments.count()}")
            for assignment in current_assignments:
                logger.info(
                    f"Assignment {assignment.id}: "
                    f"truck={assignment.truck_id}, "
                    f"status={assignment.status}"
                )
            
            # Get busy truck IDs
            busy_truck_ids = set(current_assignments.values_list('truck_id', flat=True))
            logger.info(f"[AssignmentForm.__init__] Busy truck IDs: {busy_truck_ids}")
            
            # Get final available trucks
            final_trucks = active_trucks.exclude(id__in=busy_truck_ids)
            logger.info(f"[AssignmentForm.__init__] Final available trucks: {final_trucks.count()}")
            
            # Log final available trucks
            for truck in final_trucks:
                logger.info(
                    f"Available truck: {truck.id} ({truck.unit}): "
                    f"status={truck.status}, "
                    f"duty_status={truck.duty_status}"
                )
            
            # Set the queryset
            self.fields['truck'].queryset = final_trucks
            
            # Get available drivers (using existing logic)
            available_drivers = Driver.objects.filter(
                tenant=self.tenant,
                is_active=True
            ).exclude(
                id__in=current_assignments.values_list('driver_id', flat=True)
            )
            self.fields['driver'].queryset = available_drivers
            
            # Get available dispatches
            available_dispatches = Dispatch.objects.filter(
                tenant=self.tenant,
                status=DispatchStatus.PENDING
            ).select_related('order')
            self.fields['dispatch'].queryset = available_dispatches
            
            # Log final form field states
            logger.info(f"[AssignmentForm.__init__] Final form field states:")
            logger.info(f"- Driver queryset count: {self.fields['driver'].queryset.count()}")
            logger.info(f"- Truck queryset count: {self.fields['truck'].queryset.count()}")
            logger.info(f"- Dispatch queryset count: {self.fields['dispatch'].queryset.count()}")
            
            # If we have a dispatch instance, pre-select driver and truck
            if self.dispatch_instance and self.dispatch_instance.trip:
                trip = self.dispatch_instance.trip
                if trip.driver:
                    self.fields['driver'].initial = trip.driver.id
                if trip.truck:
                    self.fields['truck'].initial = trip.truck.id
            
        except Exception as e:
            logger.error(f"[AssignmentForm.__init__] Error setting up form: {str(e)}", exc_info=True)
            # Set empty querysets as fallback
            self.fields['driver'].queryset = Driver.objects.none()
            self.fields['truck'].queryset = Truck.objects.none()
            self.fields['dispatch'].queryset = Dispatch.objects.none()

        # Set initial status for new assignments
        if not self.instance.pk:
            self.fields['status'].initial = AssignmentStatus.ASSIGNED
            self.initial['status'] = AssignmentStatus.ASSIGNED
        
        # Handle readonly state for completed/cancelled assignments
        if self.instance and self.instance.status in [
            AssignmentStatus.OFF_DUTY,
            AssignmentStatus.CANCELLED
        ]:
            self.make_all_fields_readonly()

    def make_all_fields_readonly(self):
        """Make all form fields readonly."""
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    'readonly': True,
                    'disabled': True,
                    'style': 'pointer-events: none; background-color: #e9ecef;'
                })
            else:
                field.widget.attrs.update({
                    'readonly': True,
                    'disabled': True
                })

    def clean(self):
        cleaned_data = super().clean()
        logger.info(f"[AssignmentForm.clean] Starting form validation")
        logger.info(f"[AssignmentForm.clean] Cleaned data: {cleaned_data}")

        # Get cleaned fields
        driver = cleaned_data.get('driver')
        truck = cleaned_data.get('truck')
        dispatch = cleaned_data.get('dispatch')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        # Validate required fields
        if not driver:
            raise ValidationError("Driver is required")
        if not truck:
            raise ValidationError("Truck is required")
        if not start_date:
            raise ValidationError("Start date is required")

        # If dispatch is selected, validate driver and truck match dispatch assignment
        if dispatch:
            # Check dispatch status
            if dispatch.status in [DispatchStatus.COMPLETED, DispatchStatus.CANCELLED]:
                raise ValidationError(f"Cannot create assignment for {dispatch.get_status_display().lower()} dispatch")
            
            # Validate driver matches dispatch
            if dispatch.driver and dispatch.driver != driver:
                raise ValidationError(
                    f"Selected driver ({driver.first_name} {driver.last_name}) does not match "
                    f"the driver assigned to this dispatch ({dispatch.driver.first_name} {dispatch.driver.last_name})"
                )
            
            # Validate truck matches dispatch
            if dispatch.truck and dispatch.truck != truck:
                raise ValidationError(
                    f"Selected truck ({truck.unit}) does not match "
                    f"the truck assigned to this dispatch ({dispatch.truck.unit})"
                )
            
            # Check if dispatch already has an active assignment
            existing_assignment = DriverTruckAssignment.objects.filter(
                dispatch=dispatch,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                tenant=self.tenant
            )
            
            # Exclude current instance if we're updating
            if self.instance and self.instance.pk:
                existing_assignment = existing_assignment.exclude(pk=self.instance.pk)
            
            if existing_assignment.exists():
                existing = existing_assignment.first()
                raise ValidationError(
                    f"Dispatch already has an active assignment (ID: {existing.id})"
                )

        # Validate date logic
        if end_date and start_date:
            if end_date <= start_date:
                raise ValidationError("End date must be after start date")

        # If dispatch has order dates, validate assignment dates are within reasonable bounds
        if dispatch and dispatch.order:
            order = dispatch.order
            if order.pickup_date and start_date:
                # Assignment start should not be too far before pickup
                if start_date < order.pickup_date - timezone.timedelta(hours=24):
                    raise ValidationError(
                        "Assignment start date cannot be more than 24 hours before order pickup date"
                    )
            
            if order.delivery_date and end_date:
                # Assignment end should not be too far after delivery
                if end_date > order.delivery_date + timezone.timedelta(hours=24):
                    raise ValidationError(
                        "Assignment end date cannot be more than 24 hours after order delivery date"
                    )

        # Check for scheduling conflicts (driver and truck availability)
        if driver and truck and start_date:
            conflict_end = end_date or (start_date + timezone.timedelta(days=1))
            
            # Check driver conflicts
            driver_conflicts = DriverTruckAssignment.objects.filter(
                driver=driver,
                tenant=self.tenant,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                start_date__lt=conflict_end,
                end_date__gt=start_date
            )
            
            # Exclude current instance if updating
            if self.instance and self.instance.pk:
                driver_conflicts = driver_conflicts.exclude(pk=self.instance.pk)
            
            if driver_conflicts.exists():
                conflict = driver_conflicts.first()
                raise ValidationError(
                    f"Driver {driver.first_name} {driver.last_name} is already assigned "
                    f"during this period (Assignment ID: {conflict.id})"
                )
            
            # Check truck conflicts
            truck_conflicts = DriverTruckAssignment.objects.filter(
                truck=truck,
                tenant=self.tenant,
                status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
                start_date__lt=conflict_end,
                end_date__gt=start_date
            )
            
            # Exclude current instance if updating
            if self.instance and self.instance.pk:
                truck_conflicts = truck_conflicts.exclude(pk=self.instance.pk)
            
            if truck_conflicts.exists():
                conflict = truck_conflicts.first()
                raise ValidationError(
                    f"Truck {truck.unit} is already assigned "
                    f"during this period (Assignment ID: {conflict.id})"
                )

        # Validate driver and truck belong to the same carrier (if applicable)
        if driver and truck:
            if (driver.carrier and truck.carrier and 
                driver.carrier != truck.carrier):
                raise ValidationError(
                    f"Driver ({driver.carrier.name}) and truck ({truck.carrier.name}) "
                    f"belong to different carriers"
                )

        # Validate driver employment status
        if driver:
            try:
                employment = driver.driveremployment
                logger.info(f"[AssignmentForm.clean] Found employment record for {driver.first_name} {driver.last_name}: status={employment.employment_status}")
                
                if employment.employment_status.upper() != 'ACTIVE':
                    raise ValidationError(
                        f"Driver {driver.first_name} {driver.last_name} is not currently active "
                        f"(status: {employment.get_employment_status_display()})"
                    )
            except DriverEmployment.DoesNotExist:
                logger.warning(f"[AssignmentForm.clean] No employment record found for {driver.first_name} {driver.last_name} - attempting to create one")
                # If no employment record found, try to create one automatically
                try:
                    from fleet.models.driver import DriverEmployment, EmploymentStatus, DutyStatus
                    
                    logger.info(f"[AssignmentForm.clean] Driver {driver.first_name} {driver.last_name} has no employment record")
                    logger.info(f"[AssignmentForm.clean] Driver details: is_active={driver.is_active}, termination_date={driver.termination_date}")
                    
                    # Check if driver is still considered active based on basic driver fields
                    if not driver.is_active:
                        logger.warning(f"[AssignmentForm.clean] Driver {driver.first_name} {driver.last_name} is not active")
                        raise ValidationError(
                            f"Driver {driver.first_name} {driver.last_name} is not active"
                        )
                    
                    if driver.termination_date and driver.termination_date <= timezone.now().date():
                        logger.warning(f"[AssignmentForm.clean] Driver {driver.first_name} {driver.last_name} has been terminated on {driver.termination_date}")
                        raise ValidationError(
                            f"Driver {driver.first_name} {driver.last_name} has been terminated"
                        )
                    
                    logger.info(f"[AssignmentForm.clean] Creating employment record for driver {driver.first_name} {driver.last_name}")
                    logger.info(f"[AssignmentForm.clean] Using tenant: {self.tenant}")
                    
                    # Create missing employment record
                    employment = DriverEmployment.objects.create(
                        driver=driver,
                        tenant=self.tenant,
                        employment_status=EmploymentStatus.ACTIVE,
                        duty_status=DutyStatus.AVAILABLE,
                    )
                    
                    logger.info(f"[AssignmentForm.clean] Successfully created missing employment record for driver {driver.first_name} {driver.last_name}")
                    
                except ValidationError:
                    # Re-raise validation errors (these are expected)
                    raise
                except Exception as e:
                    logger.error(f"[AssignmentForm.clean] Failed to create employment record for {driver.first_name} {driver.last_name}: {str(e)}", exc_info=True)
                    
                    # Instead of failing completely, log a warning and continue
                    # This allows the assignment to proceed while we fix the underlying issue
                    logger.warning(f"[AssignmentForm.clean] Proceeding with assignment despite employment record issue for {driver.first_name} {driver.last_name}")
                    
                    # You could optionally show a warning message to the user
                    # by adding a non-field error that doesn't stop form submission
                    self.add_error(None, 
                        f"Warning: Driver {driver.first_name} {driver.last_name} has no employment record. "
                        f"The assignment will be created, but please contact an administrator to resolve the employment record issue."
                    )
            except Exception as e:
                logger.error(f"[AssignmentForm.clean] Unexpected error accessing employment record for {driver.first_name} {driver.last_name}: {str(e)}", exc_info=True)
                self.add_error(None, 
                    f"Warning: Unable to verify employment status for {driver.first_name} {driver.last_name}. "
                    f"The assignment will be created, but please contact an administrator to resolve this issue."
                )

        # Validate truck status
        if truck:
            if truck.status.upper() != 'ACTIVE':
                raise ValidationError(
                    f"Truck {truck.unit} is not currently active (status: {truck.get_status_display()})"
                )

        logger.info(f"[AssignmentForm.clean] Validation completed successfully")
        return cleaned_data

    def is_assignment_available(self, driver, truck, start_date, end_date):
        """Check if driver and truck are available for the assignment period."""
        if not end_date:
            end_date = start_date + timezone.timedelta(days=365)  # Default to one year

        # Check for conflicting assignments
        conflicting_assignments = DriverTruckAssignment.objects.filter(
            Q(driver=driver) | Q(truck=truck),
            tenant=self.tenant,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY],
            start_date__lt=end_date,
            end_date__gt=start_date
        )

        # Exclude current instance if updating
        if self.instance and self.instance.pk:
            conflicting_assignments = conflicting_assignments.exclude(pk=self.instance.pk)

        return not conflicting_assignments.exists()

    def save(self, commit=True):
        """Save the assignment."""
        try:
            instance = super().save(commit=False)
            
            if self.tenant:
                instance.tenant = self.tenant
                
                # Get the driver and truck from cleaned data
                driver = self.cleaned_data.get('driver')
                truck = self.cleaned_data.get('truck')
                
                # Try to get carrier in this order:
                # 1. From driver's carrier
                # 2. From truck's carrier
                # 3. From tenant's default carrier
                carrier = None
                
                if driver and driver.carrier:
                    carrier = driver.carrier
                    logger.info(f"[AssignmentForm.save] Using carrier from driver: {carrier}")
                elif truck and truck.carrier:
                    carrier = truck.carrier
                    logger.info(f"[AssignmentForm.save] Using carrier from truck: {carrier}")
                elif self.tenant and hasattr(self.tenant, 'default_carrier'):
                    carrier = self.tenant.default_carrier
                    logger.info(f"[AssignmentForm.save] Using default carrier from tenant: {carrier}")
                
                if carrier:
                    instance.carrier = carrier
                else:
                    logger.error("[AssignmentForm.save] No carrier found from driver, truck, or tenant")
                    raise ValidationError(
                        "A carrier is required. Please ensure either the driver or truck has an assigned carrier, "
                        "or that a default carrier is set for the tenant."
                    )
            
            if commit:
                instance.save()
            
            return instance
            
        except Exception as e:
            logger.error(f"[AssignmentForm.save] Error saving assignment: {str(e)}", exc_info=True)
            raise ValidationError(f"Error saving assignment: {str(e)}") 