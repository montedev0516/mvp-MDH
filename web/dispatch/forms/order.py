from django import forms
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from models.models import Currency
from dispatch.models import Order, OrderStatus
from fleet.models import Customer
import logging

logger = logging.getLogger(__name__)

class OrderBaseForm(forms.ModelForm):
    """Base form for order creation and updates."""
    
    customer_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Customer Name"
        })
    )
    
    customer_address = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Customer Address"
        })
    )
    
    customer_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "type": "email",
            "placeholder": "customer@example.com"
        })
    )
    
    customer_phone = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "type": "tel",
            "placeholder": "+1 (555) 555-5555"
        })
    )
    
    order_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Order Number"
        })
    )
    
    pickup_date = forms.DateTimeField(
        required=True,
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(
            attrs={
                "class": "form-control",
                "type": "datetime-local"
            },
            format="%Y-%m-%dT%H:%M"
        )
    )
    
    delivery_date = forms.DateTimeField(
        required=True,
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(
            attrs={
                "class": "form-control",
                "type": "datetime-local"
            },
            format="%Y-%m-%dT%H:%M"
        )
    )
    
    origin = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Origin Address"
        })
    )
    
    destination = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Destination Address"
        })
    )
    
    cargo_type = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Type of Cargo"
        })
    )
    
    weight = forms.FloatField(
        min_value=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0",
            "placeholder": "Weight in kg/lbs"
        })
    )
    
    status = forms.CharField(
        required=False,  # Make it not required since we'll set it programmatically
        widget=forms.HiddenInput(),  # Hide it from the form
        initial='pending'  # Set default value
    )
    
    remarks_or_special_instructions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Enter any special instructions or remarks..."
        })
    )
    
    load_total = forms.FloatField(
        min_value=0,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
            "min": "0"
        })
    )
    
    load_currency = forms.ChoiceField(
        choices=Currency.choices,
        widget=forms.Select(attrs={
            "class": "form-select"
        })
    )

    class Meta:
        model = Order
        fields = [
            'order_number',
            'customer_name',
            'customer_address',
            'customer_email',
            'customer_phone',
            'origin',
            'destination',
            'cargo_type',
            'weight',
            'pickup_date',
            'delivery_date',
            'load_total',
            'load_currency',
            'status',
            'remarks_or_special_instructions'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial values for dates if instance exists
        if self.instance and self.instance.pk:
            if self.instance.pickup_date:
                self.initial['pickup_date'] = self.instance.pickup_date.strftime('%Y-%m-%dT%H:%M')
            if self.instance.delivery_date:
                self.initial['delivery_date'] = self.instance.delivery_date.strftime('%Y-%m-%dT%H:%M')

    def clean(self):
        """Validate form data."""
        cleaned_data = super().clean()
        
        # Check required fields
        required_fields = [
            'order_number', 'customer_name', 'origin', 'destination',
            'cargo_type', 'weight', 'pickup_date', 'delivery_date',
            'load_total', 'load_currency'
        ]
        
        for field in required_fields:
            if not cleaned_data.get(field):
                self.add_error(field, 'This field is required.')
        
        # Always set status to pending for new orders
        cleaned_data['status'] = OrderStatus.PENDING
        
        # Validate dates
        pickup_date = cleaned_data.get('pickup_date')
        delivery_date = cleaned_data.get('delivery_date')
        
        if pickup_date and delivery_date:
            if pickup_date > delivery_date:
                raise ValidationError({
                    'delivery_date': 'Delivery date must be after pickup date'
                })
            
            # Only validate future dates for new orders that are not from PDF
            if not self.instance.pk and not getattr(self.instance, 'pdf', None):
                if pickup_date < timezone.now() - timezone.timedelta(minutes=1):
                    raise ValidationError({
                        'pickup_date': 'Pickup date cannot be in the past'
                    })
        
        return cleaned_data


class OrderForm(OrderBaseForm):
    """Form for creating new orders."""
    
    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        
        # Set initial values
        self.fields['load_currency'].initial = Currency.CAD
        self.fields['status'].initial = OrderStatus.PENDING

    def clean(self):
        """Validate form data."""
        cleaned_data = super().clean()
        
        # Check required fields
        required_fields = [
            'order_number', 'customer_name', 'origin', 'destination',
            'cargo_type', 'weight', 'pickup_date', 'delivery_date',
            'load_total', 'load_currency'
        ]
        
        for field in required_fields:
            if not cleaned_data.get(field):
                self.add_error(field, 'This field is required.')
        
        # Always set status to pending for new orders
        cleaned_data['status'] = OrderStatus.PENDING
        
        # Validate dates
        pickup_date = cleaned_data.get('pickup_date')
        delivery_date = cleaned_data.get('delivery_date')
        
        if pickup_date and delivery_date:
            if pickup_date > delivery_date:
                raise ValidationError({
                    'delivery_date': 'Delivery date must be after pickup date'
                })
            
            if pickup_date < timezone.now() - timezone.timedelta(minutes=1):
                raise ValidationError({
                    'pickup_date': 'Pickup date cannot be in the past'
                })
        
        # Validate load total
        load_total = cleaned_data.get('load_total')
        if load_total and load_total <= 0:
            raise ValidationError({
                'load_total': 'Load total must be greater than 0'
            })
        
        # Validate weight
        weight = cleaned_data.get('weight')
        if weight and weight <= 0:
            raise ValidationError({
                'weight': 'Weight must be greater than 0'
            })
        
        return cleaned_data

    def save(self, commit=True):
        """Save the order and create/update customer if needed."""
        instance = super().save(commit=False)
        instance.tenant = self.tenant
        instance.status = OrderStatus.PENDING  # Ensure status is set
        
        if commit:
            try:
                with transaction.atomic():
                    # Create or update customer
                    customer_data = {
                        'name': self.cleaned_data['customer_name'],
                        'address': self.cleaned_data.get('customer_address', ''),
                        'email': self.cleaned_data.get('customer_email', ''),
                        'phone': self.cleaned_data.get('customer_phone', ''),
                        'tenant': self.tenant
                    }
                    
                    customer, created = Customer.objects.update_or_create(
                        name__iexact=customer_data['name'],
                        tenant=self.tenant,
                        defaults=customer_data
                    )
                    
                    # Set the customer relationship
                    instance.customer = customer
                    
                    # Set default values for AI processing fields
                    instance.raw_extract = {}
                    instance.raw_text = ""
                    instance.completion_tokens = 0
                    instance.prompt_tokens = 0
                    instance.total_tokens = 0
                    instance.llm_model_name = ""
                    instance.usage_details = {}
                    instance.processed = False
                    
                    # Save the order
                    instance.save()
                    
            except Exception as e:
                logger.error(f"Error saving order: {str(e)}")
                raise ValidationError(f"Error saving order: {str(e)}")
        
        return instance


class OrderUpdateForm(OrderBaseForm):
    """Form for updating existing orders."""
    
    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        
        # Make order number read-only
        self.fields["order_number"].widget.attrs["readonly"] = True

        # Populate initial customer data
        if self.instance and self.instance.customer:
            self.fields["customer_name"].initial = self.instance.customer.name
            self.fields["customer_address"].initial = self.instance.customer.address
            self.fields["customer_email"].initial = self.instance.customer.email
            self.fields["customer_phone"].initial = self.instance.customer.phone

        # Log initial state
        logger.info(f"Form initialized with instance: {self.instance.pk}")
        logger.info(f"Initial pickup_date: {self.instance.pickup_date}")
        logger.info(f"Initial delivery_date: {self.instance.delivery_date}")

    def clean_order_number(self):
        # Return the original order number since it's read-only
        return self.instance.order_number

    def clean(self):
        cleaned_data = super().clean()
        pickup_date = cleaned_data.get("pickup_date")
        delivery_date = cleaned_data.get("delivery_date")

        logger.info(f"Cleaned pickup_date: {pickup_date}")
        logger.info(f"Cleaned delivery_date: {delivery_date}")

        if pickup_date and delivery_date and pickup_date > delivery_date:
            raise ValidationError("Pickup date cannot be later than delivery date")

        # Don't override the status if it's not in the form data
        if 'status' not in self.data:
            cleaned_data['status'] = self.instance.status

        return cleaned_data

    def save(self, commit=True):
        """Save the order and update customer if needed."""
        try:
            with transaction.atomic():
                # Get the instance but don't save it yet
                instance = super().save(commit=False)
                
                logger.info("Before save:")
                logger.info(f"Instance ID: {instance.pk}")
                logger.info(f"Changed data: {self.changed_data}")
                logger.info(f"Cleaned data: {self.cleaned_data}")
                
                # Preserve existing data that shouldn't be overwritten
                instance.tenant = self.tenant or instance.tenant
                instance.raw_extract = instance.raw_extract or {}
                instance.raw_text = instance.raw_text or ""
                instance.completion_tokens = instance.completion_tokens or 0
                instance.prompt_tokens = instance.prompt_tokens or 0
                instance.total_tokens = instance.total_tokens or 0
                instance.llm_model_name = instance.llm_model_name or ""
                instance.usage_details = instance.usage_details or {}
                instance.processed = instance.processed  # Keep existing processed state
                
                # Update fields from cleaned_data
                update_fields = [
                    'customer_name', 'customer_address', 'customer_email', 'customer_phone',
                    'origin', 'destination', 'cargo_type', 'weight',
                    'pickup_date', 'delivery_date', 'load_total', 'load_currency',
                    'remarks_or_special_instructions'
                ]
                
                for field in update_fields:
                    if field in self.cleaned_data:
                        value = self.cleaned_data[field]
                        logger.info(f"Setting {field} = {value}")
                        setattr(instance, field, value)
                
                if commit:
                    # Update customer if exists
                    if instance.customer:
                        customer = instance.customer
                        customer.name = self.cleaned_data['customer_name']
                        customer.address = self.cleaned_data.get('customer_address', '')
                        customer.email = self.cleaned_data.get('customer_email', '')
                        customer.phone = self.cleaned_data.get('customer_phone', '')
                        customer.save()
                    else:
                        # Create new customer if none exists
                        customer = Customer.objects.create(
                            tenant=self.tenant,
                            name=self.cleaned_data['customer_name'],
                            address=self.cleaned_data.get('customer_address', ''),
                            email=self.cleaned_data.get('customer_email', ''),
                            phone=self.cleaned_data.get('customer_phone', '')
                        )
                        instance.customer = customer
                    
                    # Save the instance
                    instance.save()
                    
                    # Verify the save
                    saved_instance = Order.objects.get(pk=instance.pk)
                    logger.info("After save:")
                    for field in update_fields:
                        logger.info(f"{field}: {getattr(saved_instance, field)}")
                
                return instance
                
        except Exception as e:
            logger.error(f"Error in save method: {str(e)}", exc_info=True)
            raise ValidationError(f"Error updating order: {str(e)}")
