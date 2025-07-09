from django import forms
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
from models.models import Currency
from dispatch.models import (
    Trip, TripStatus
)
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

class TripForm(forms.ModelForm):
    """Form for creating and updating trips."""

    # Trip planning fields
    estimated_distance = forms.FloatField(
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "placeholder": "Enter estimated distance"
        }),
        required=True,
        validators=[MinValueValidator(0)],
        help_text="Distance in kilometers",
    )

    estimated_duration_hours = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "placeholder": "Hours"
        }),
        required=True,
        help_text="Estimated hours of travel",
    )

    estimated_duration_minutes = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "min": "0",
            "max": "59",
            "placeholder": "Minutes"
        }),
        required=True,
        help_text="Estimated minutes of travel",
    )

    # Cost estimate fields
    fuel_estimated = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "placeholder": "Estimated fuel cost"
        }),
        required=True,
        validators=[MinValueValidator(0)],
        help_text="Estimated fuel cost for the trip",
    )

    toll_estimated = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "placeholder": "Estimated toll cost"
        }),
        required=False,
        validators=[MinValueValidator(0)],
        help_text="Estimated toll costs along the route",
    )

    freight_estimated = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "placeholder": "Estimated freight value"
        }),
        required=True,
        validators=[MinValueValidator(0)],
        help_text="Estimated value of the freight being transported",
    )

    # Financial fields
    freight_value = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "placeholder": "Actual freight value"
        }),
        required=True,
        validators=[MinValueValidator(0)],
        help_text="Actual freight value for billing purposes",
    )

    currency = forms.ChoiceField(
        choices=Currency.choices,
        widget=forms.Select(attrs={
            "class": "form-select"
        }),
        required=True,
        help_text="Currency for all financial values",
    )

    freight_value_currency = forms.ChoiceField(
        choices=Currency.choices,
        widget=forms.HiddenInput(),
        required=False,
    )

    status = forms.ChoiceField(
        choices=TripStatus.choices,
        widget=forms.HiddenInput(),
        required=True,
        initial=TripStatus.PENDING,
    )

    notes = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Enter any notes about the trip..."
        }),
        required=False,
    )

    class Meta:
        model = Trip
        fields = [
            "estimated_distance",
            "fuel_estimated",
            "toll_estimated",
            "freight_estimated",
            "currency",
            "freight_value",
            "freight_value_currency",
            "status",
            "notes",
        ]
        exclude = ["estimated_duration", "route", "stops"]

    def __init__(self, *args, **kwargs):
        # Extract parameters from kwargs
        self.tenant = kwargs.pop("tenant", None)
        self.order_instance = kwargs.pop("order", None)

        super().__init__(*args, **kwargs)

        # Set initial values if order is provided
        if self.order_instance:
            self.fields["currency"].initial = self.order_instance.load_currency

        # Handle readonly state for completed/cancelled trips
        if self.instance and self.instance.status in [TripStatus.COMPLETED, TripStatus.CANCELLED]:
            self.make_all_fields_readonly()

        # Set initial values for duration fields if instance exists
        if self.instance and self.instance.pk and self.instance.estimated_duration:
            total_seconds = int(self.instance.estimated_duration.total_seconds())
            self.fields['estimated_duration_hours'].initial = total_seconds // 3600
            self.fields['estimated_duration_minutes'].initial = (total_seconds % 3600) // 60

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
        """Validate form data."""
        cleaned_data = super().clean()
        
        # Get values for validation
        freight_value = cleaned_data.get("freight_value")
        freight_estimated = cleaned_data.get("freight_estimated")
        
        if freight_value is not None and freight_estimated is not None:
            # Convert to Decimal for comparison
            freight_value = Decimal(str(freight_value))
            freight_estimated = Decimal(str(freight_estimated))
            
            # Only validate if estimated value is greater than zero
            if freight_estimated > 0:
                min_value = freight_estimated * Decimal('0.5')
                logger.info(f"[TripForm.clean] Comparing freight values - actual: {freight_value}, min required (50% of estimated): {min_value}")
                
                if freight_value < min_value:
                    error_msg = f'Actual freight value ({freight_value}) must be at least {min_value} (50% of estimated value {freight_estimated})'
                    logger.error(f"[TripForm.clean] Validation error: {error_msg}")
                    self.add_error('freight_value', error_msg)

        # Validate status transition if this is an update
        if self.instance and self.instance.pk:
            new_status = cleaned_data.get('status')
            if new_status and new_status != self.instance.status:
                try:
                    self.instance.validate_status_transition(new_status)
                except ValidationError as e:
                    self.add_error('status', str(e))

        # Check that order is available for this trip
        if not self.order_instance and not hasattr(self, "instance") and not getattr(self.instance, "order", None):
            raise ValidationError("Order is required for trip creation")

        # Ensure status is set
        if 'status' not in cleaned_data or not cleaned_data.get('status'):
            cleaned_data['status'] = TripStatus.PENDING
            logger.info("Setting default status in clean method")

        # Validate duration fields
        hours = cleaned_data.get('estimated_duration_hours', 0)
        minutes = cleaned_data.get('estimated_duration_minutes', 0)
        
        if hours is None or minutes is None:
            self.add_error('estimated_duration_hours', 'Both hours and minutes must be provided')
        elif hours < 0 or minutes < 0:
            self.add_error('estimated_duration_hours', 'Duration cannot be negative')
        elif minutes >= 60:
            self.add_error('estimated_duration_minutes', 'Minutes must be less than 60')

        logger.info(f"[TripForm.clean] Final cleaned_data: {cleaned_data}")
        return cleaned_data

    def save(self, commit=True):
        """Save the form and handle duration conversion."""
        instance = super().save(commit=False)
        logger.info(f"🙌[TripForm.save] Instance: {instance}")

        # Convert hours and minutes to duration
        hours = self.cleaned_data.get("estimated_duration_hours", 0) or 0
        minutes = self.cleaned_data.get("estimated_duration_minutes", 0) or 0
        instance.estimated_duration = timedelta(hours=hours, minutes=minutes)
        
        # Set the freight_value_currency to match the currency
        instance.freight_value_currency = instance.currency
        
        if commit:
            instance.save()
        
        return instance
