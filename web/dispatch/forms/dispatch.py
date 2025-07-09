from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from models.models import Currency
from dispatch.models import (
    Dispatch,
    DispatchStatus,
    Trip,
    TripStatus,
    Order,
    DriverTruckAssignment,
    AssignmentStatus,
    StatusHistory
)
from fleet.models import Customer, Driver, Truck, Carrier, DutyStatus, TruckDutyStatus
import logging
from decimal import Decimal, ROUND_HALF_UP
from dispatch.utils import check_resource_availability_with_lock

logger = logging.getLogger(__name__)

class DispatchForm(forms.ModelForm):
    LIMITED_STATUS_CHOICES = [
        (DispatchStatus.PENDING, "Pending"),
        (DispatchStatus.ASSIGNED, "Assigned"),
        (DispatchStatus.IN_TRANSIT, "In Transit"),
        (DispatchStatus.DELIVERED, "Delivered"),
        (DispatchStatus.INVOICED, "Invoiced"),
        (DispatchStatus.PAYMENT_RECEIVED, "Payment Received"),
        (DispatchStatus.COMPLETED, "Completed"),
        (DispatchStatus.CANCELLED, "Cancelled"),
    ]

    order_number = forms.CharField(required=True, widget=forms.HiddenInput())
    order_date = forms.DateTimeField(required=True, widget=forms.HiddenInput())
    
    trip = forms.ModelChoiceField(
        queryset=Trip.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Trip"
        })
    )
    
    driver = forms.ModelChoiceField(
        queryset=Driver.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Driver"
        })
    )
    
    truck = forms.ModelChoiceField(
        queryset=Truck.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Truck"
        })
    )
    
    carrier = forms.ModelChoiceField(
        queryset=Carrier.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Carrier"
        })
    )
    
    status = forms.ChoiceField(
        choices=LIMITED_STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    commission_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "readonly": True,
            "step": "0.01",
            "id": "id_commission_amount",
            "data-commission-amount": True
        }),
    )

    commission_percentage = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        initial=12.0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "max": "100",
            "id": "id_commission_percentage",
            "data-commission-percentage": True
        }),
    )

    commission_currency = forms.ChoiceField(
        choices=Currency.choices,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Currency"
        }),
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    class Meta:
        model = Dispatch
        fields = [
            "order_number",
            "order_date",
            "customer",
            "trip",
            "driver",
            "truck",
            "carrier",
            "notes",
            "commission_amount",
            "commission_percentage",
            "commission_currency",
            "status",
        ]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop("tenant", None)
        super().__init__(*args, **kwargs)

        if self.tenant:
            # Filter querysets by tenant
            self.fields["trip"].queryset = Trip.objects.filter(tenant=self.tenant)
            self.fields["driver"].queryset = Driver.objects.filter(tenant=self.tenant)
            self.fields["truck"].queryset = Truck.objects.filter(tenant=self.tenant)
            self.fields["carrier"].queryset = Carrier.objects.filter(tenant=self.tenant)
            self.fields["customer"].queryset = Customer.objects.filter(tenant=self.tenant)

        # Set initial commission currency
        if not self.instance.pk:
            self.fields["commission_currency"].initial = Currency.CAD

    def are_resources_available(self, driver, truck, trip):
        """Check if driver and truck are available for the trip period using enhanced validation"""
        if not trip or not trip.order:
            return True

        start_date = trip.order.pickup_date or timezone.now()
        end_date = trip.order.delivery_date
        if not end_date and trip.estimated_duration:
            end_date = start_date + trip.estimated_duration

        # Use the enhanced resource availability check with locking
        exclude_assignment_id = None
        if self.instance and hasattr(self.instance, 'assignments'):
            # Exclude current assignment if updating
            current_assignment = self.instance.assignments.first()
            if current_assignment:
                exclude_assignment_id = current_assignment.id
        
        is_available, reason = check_resource_availability_with_lock(
            driver_id=driver.id,
            truck_id=truck.id, 
            start_date=start_date,
            end_date=end_date,
            exclude_assignment_id=exclude_assignment_id
        )
        
        if not is_available:
            logger.warning(f"Resource availability check failed: {reason}")
            
        return is_available

    def clean(self):
        """Enhanced validation with better error messages"""
        cleaned_data = super().clean()
        
        # Get required fields
        status = cleaned_data.get("status")
        driver = cleaned_data.get("driver")
        truck = cleaned_data.get("truck")
        carrier = cleaned_data.get("carrier")
        trip = cleaned_data.get("trip")
        commission_percentage = cleaned_data.get("commission_percentage")

        # Collect all validation errors
        validation_errors = {}

        # Validate status requirements
        if status == DispatchStatus.ASSIGNED:
            if not driver:
                validation_errors["driver"] = "Driver assignment is required when status is 'Assigned'. Please select a driver."
            if not truck:
                validation_errors["truck"] = "Truck assignment is required when status is 'Assigned'. Please select a truck."
            
        # Validate driver-truck compatibility
        if driver and truck:
            # Check if driver is qualified for this truck type
            is_qualified, reason = driver.is_qualified_for_truck(truck)
            if not is_qualified:
                validation_errors["driver"] = f"Driver compatibility issue: {reason}. Please check driver qualifications and license status."
            
            # Check if driver and truck are available
            elif not self.are_resources_available(driver, truck, trip):
                validation_errors["__all__"] = [
                    "Resource scheduling conflict detected. The selected driver or truck is not available during the trip period.",
                    "Please choose different resources or adjust the trip dates."
                ]

        # Validate carrier assignment
        if carrier and driver and driver.carrier != carrier:
            validation_errors["carrier"] = f"Carrier mismatch: Driver '{driver.get_full_name()}' belongs to '{driver.carrier}', not '{carrier}'. Please select the correct carrier or choose a different driver."

        # Validate commission calculations
        if commission_percentage is not None:
            if commission_percentage < 0:
                validation_errors["commission_percentage"] = "Commission percentage cannot be negative."
            elif commission_percentage > 100:
                validation_errors["commission_percentage"] = "Commission percentage cannot exceed 100%."
            
            # Calculate commission amount
            if self.instance and hasattr(self.instance, "order"):
                order = self.instance.order
                if order and order.load_total:
                    try:
                        load_total = float(order.load_total)
                        if load_total > 0:
                            # Calculate with Decimal for precision and round to 2 decimal places
                            commission_amount = Decimal(str(load_total)) * (Decimal(str(commission_percentage)) / Decimal('100'))
                            cleaned_data["commission_amount"] = commission_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    except (ValueError, TypeError) as e:
                        validation_errors["commission_percentage"] = f"Error calculating commission: {str(e)}"

        # Validate trip assignment
        if trip and self.instance and hasattr(self.instance, 'order'):
            if trip.order != self.instance.order:
                validation_errors["trip"] = "Selected trip does not belong to this dispatch's order. Please select a valid trip."

        # Ensure commission currency is set
        if not cleaned_data.get("commission_currency"):
            cleaned_data["commission_currency"] = Currency.CAD

        # Raise all validation errors at once
        if validation_errors:
            raise ValidationError(validation_errors)

        return cleaned_data

    def save(self, commit=True):
        """Save the dispatch and create associated DriverTruckAssignment if needed."""
        instance = super().save(commit=False)
        
        if self.tenant:
            instance.tenant = self.tenant
        
        if commit:
            try:
                with transaction.atomic():
                    # Save the dispatch first
                    instance.save()
                    
                    # Get the cleaned data
                    driver = self.cleaned_data.get('driver')
                    truck = self.cleaned_data.get('truck')
                    carrier = self.cleaned_data.get('carrier')
                    trip = self.cleaned_data.get('trip')
                    
                    # If we have driver and truck, create DriverTruckAssignment
                    if driver and truck:
                        # Get dates from trip or use defaults
                        start_date = trip.order.pickup_date if trip and trip.order else timezone.now()
                        end_date = trip.order.delivery_date if trip and trip.order else None
                        
                        # Create the assignment
                        assignment = DriverTruckAssignment.objects.create(
                            driver=driver,
                            truck=truck,
                            dispatch=instance,
                            tenant=instance.tenant,
                            carrier=carrier or driver.carrier,
                            start_date=start_date,
                            end_date=end_date,
                            status=AssignmentStatus.ASSIGNED if instance.status == DispatchStatus.ASSIGNED else AssignmentStatus.UNASSIGNED
                        )
                    
            except Exception as e:
                logger.error(f"Error saving dispatch: {str(e)}")
                raise ValidationError(f"Error saving dispatch: {str(e)}")
        
        return instance


class DispatchDetailForm(forms.ModelForm):
    """Form for updating dispatch details"""

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        is_readonly = kwargs.pop('is_readonly', False)
        super().__init__(*args, **kwargs)
        
        # Update querysets based on tenant if provided
        if tenant:
            if 'customer' in self.fields:
                self.fields['customer'].queryset = Customer.objects.filter(tenant=tenant)
            if 'driver' in self.fields:
                from fleet.models import Driver
                self.fields['driver'].queryset = Driver.objects.filter(tenant=tenant)
            if 'truck' in self.fields:
                from fleet.models import Truck
                self.fields['truck'].queryset = Truck.objects.filter(tenant=tenant)
            if 'carrier' in self.fields:
                from fleet.models import Carrier
                self.fields['carrier'].queryset = Carrier.objects.filter(tenant=tenant)
            if 'trip' in self.fields and self.instance and self.instance.order:
                # Filter trips by order and tenant
                self.fields['trip'].queryset = Trip.objects.filter(
                    order=self.instance.order,
                    tenant=tenant
                )

        # Set initial commission currency
        if not self.instance.pk:
            self.fields["commission_currency"].initial = Currency.CAD

        # Handle readonly fields
        if is_readonly or (self.instance and self.instance.status in [
            DispatchStatus.INVOICED,
            DispatchStatus.PAYMENT_RECEIVED,
            DispatchStatus.CANCELLED
        ]):
            self.make_all_fields_readonly()

    def make_all_fields_readonly(self):
        """Make all form fields readonly"""
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
    
    order_number = forms.CharField(
        disabled=False,
        widget=forms.TextInput(attrs={"class": "form-control", "readonly": True})
    )
    order_date = forms.DateTimeField(
        disabled=False,
        widget=forms.DateTimeInput(
            attrs={"class": "form-control", "type": "datetime-local", "readonly": True},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        disabled=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    trip = forms.ModelChoiceField(
        queryset=Trip.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Trip",
            "data-trip-select": True
        }),
    )
    driver = forms.ModelChoiceField(
        queryset=Driver.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Driver",
            "data-driver-select": True
        }),
    )
    truck = forms.ModelChoiceField(
        queryset=Truck.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Truck",
            "data-truck-select": True
        }),
    )
    carrier = forms.ModelChoiceField(
        queryset=Carrier.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            "class": "form-select",
            "data-placeholder": "Select Carrier",
            "data-carrier-select": True
        }),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    commission_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "readonly": True,
            "step": "0.01",
            "data-allow-edit": "true"  # Special flag to allow updates via calculation
        }),
    )
    commission_percentage = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        initial=12.0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "max": "100"
        }),
    )
    commission_currency = forms.ChoiceField(
        choices=Currency.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = forms.ChoiceField(
        choices=DispatchStatus.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Dispatch
        fields = [
            "order_number",
            "order_date",
            "customer",
            "trip",
            "driver",
            "truck",
            "carrier",
            "notes",
            "commission_amount",
            "commission_percentage",
            "commission_currency",
            "status",
        ]

    def clean(self):
        cleaned_data = super().clean()
        logger = logging.getLogger("django")

        # Get required fields
        status = cleaned_data.get("status")
        driver = cleaned_data.get("driver")
        truck = cleaned_data.get("truck")
        carrier = cleaned_data.get("carrier")
        trip = cleaned_data.get("trip")
        commission_percentage = cleaned_data.get("commission_percentage")

        # Validate status requirements
        if status == DispatchStatus.ASSIGNED:
            if not driver:
                raise ValidationError({"driver": "Driver is required for Assigned status"})
            if not truck:
                raise ValidationError({"truck": "Truck is required for Assigned status"})
            
        # Validate driver-truck compatibility
        if driver and truck:
            # Check if driver is qualified for this truck type
            if not driver.is_qualified_for_truck(truck):
                raise ValidationError({
                    "driver": f"Driver {driver} is not qualified to operate truck {truck}"
                })

        # Validate carrier assignment
        if carrier and driver and driver.carrier != carrier:
            raise ValidationError({
                "carrier": f"Driver {driver} does not belong to carrier {carrier}"
            })

        # Validate commission calculations
        if commission_percentage is not None:
            if commission_percentage < 0 or commission_percentage > 100:
                raise ValidationError({
                    "commission_percentage": "Commission percentage must be between 0 and 100"
                })
            
            # Calculate commission amount
            if self.instance and hasattr(self.instance, "order"):
                order = self.instance.order
                if order and order.load_total:
                    load_total = float(order.load_total)
                    if load_total > 0:
                        # Calculate with Decimal for precision and round to 2 decimal places
                        commission_amount = Decimal(str(load_total)) * (Decimal(str(commission_percentage)) / Decimal('100'))
                        cleaned_data["commission_amount"] = commission_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Ensure commission currency is set
        if not cleaned_data.get("commission_currency"):
            cleaned_data["commission_currency"] = Currency.CAD

        return cleaned_data
