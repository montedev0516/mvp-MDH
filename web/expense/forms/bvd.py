import logging
from django import forms
from django.utils import timezone
from expense.models import BVD, AccountPayableStatus
from models.models import Currency

logger = logging.getLogger("django")


class BVDForm(forms.ModelForm):
    """Form for BVD (Bulk Vehicle Data) records"""
    
    class Meta:
        model = BVD
        exclude = ["tenant", "is_active", "deleted_at"]
        widgets = {
            "date": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control",
                    "required": "required"
                },
                format="%Y-%m-%dT%H:%M"
            ),
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "card_number": forms.TextInput(attrs={"class": "form-control"}),
            "time": forms.TextInput(attrs={"class": "form-control"}),
            "auth_code": forms.TextInput(attrs={"class": "form-control"}),
            "unit": forms.NumberInput(attrs={"class": "form-control"}),
            "odometer": forms.NumberInput(attrs={"class": "form-control"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "uom": forms.TextInput(attrs={"class": "form-control"}),
            "retail_ppu": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "billed_ppu": forms.NumberInput(attrs={"class": "form-control", "step": "0.0001"}),
            "pre_tax_amt": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "currency": forms.Select(attrs={"class": "form-control"}, choices=Currency.choices),
            "pst": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "gst": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "hst": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "qst": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "discount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "site_number": forms.TextInput(attrs={"class": "form-control"}),
            "site_name": forms.TextInput(attrs={"class": "form-control"}),
            "site_city": forms.TextInput(attrs={"class": "form-control"}),
            "prov_st": forms.TextInput(attrs={"class": "form-control"}),
            "transaction_id": forms.TextInput(attrs={"class": "form-control"}),
            "import_batch": forms.TextInput(attrs={"class": "form-control"}),
            "driver": forms.Select(attrs={"class": "form-control"}),
            "truck": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}, choices=AccountPayableStatus.choices),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        logger.info("Initializing BVDForm")
        super().__init__(*args, **kwargs)
        
        # Make required fields
        required_fields = [
            "date", "company_name", "card_number", "unit", "quantity", 
            "retail_ppu", "billed_ppu", "pre_tax_amt", "amount", "currency",
            "site_number", "site_name", "site_city", "prov_st"
        ]
        for field in required_fields:
            self.fields[field].required = True
            
        # Set default values
        self.fields["currency"].initial = Currency.CAD
        self.fields["status"].initial = AccountPayableStatus.PENDING
        self.fields["uom"].initial = "L"
        
        # Set input formats for date field
        self.fields["date"].input_formats = [
            "%Y-%m-%dT%H:%M",  # HTML5 datetime-local
            "%Y-%m-%d %H:%M:%S",  # Standard datetime
            "%Y-%m-%d %H:%M",  # Standard datetime without seconds
            "%Y-%m-%d",  # Just date
        ]
        
        # Set initial date if not provided
        if not self.instance.pk and not self.initial.get('date'):
            self.initial['date'] = timezone.now()
        
        # Filter querysets by tenant if provided
        if tenant:
            if "driver" in self.fields:
                self.fields["driver"].queryset = self.fields["driver"].queryset.filter(
                    tenant=tenant,
                    is_active=True
                )
            if "truck" in self.fields:
                self.fields["truck"].queryset = self.fields["truck"].queryset.filter(
                    tenant=tenant,
                    is_active=True
                )
            
            # Store tenant for validation
            self._tenant = tenant
            
            # Set tenant on instance to prevent validation errors
            if hasattr(self, "instance"):
                self.instance.tenant = tenant

    def clean(self):
        logger.info("Starting BVDForm cleaning")
        cleaned_data = super().clean()
        
        # Validate amount is positive
        amount = cleaned_data.get("amount")
        if amount and amount <= 0:
            self.add_error("amount", "Amount must be greater than 0")
            
        # Validate quantity is positive
        quantity = cleaned_data.get("quantity")
        if quantity and quantity <= 0:
            self.add_error("quantity", "Quantity must be greater than 0")
            
        # Validate date is provided
        date = cleaned_data.get("date")
        if not date:
            self.add_error("date", "Date is required")
            
        return cleaned_data
